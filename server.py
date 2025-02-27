from flask import Flask, request, jsonify, render_template, send_file, send_from_directory, abort
import threading
import os
from io import BytesIO
import tempfile
import holoviews as hv
import matplotlib
matplotlib.use('Agg')

# from openhsi.cameras import FlirCamera as openhsiCamera
from openhsi.capture import SimulatedCamera as openhsiCamera

app = Flask(__name__)

# Define the list of settings to show.
SETTING_KEYS = ["n_lines", "exposure_ms", "processing_lvl"]

# Allowed processing levels with updated descriptions.
PROCESSING_LVL_OPTIONS = {
    -1: "-1 - do not apply any transforms (default)",
     0: "0 - crop to useable sensor area",
     1: "1 - crop + fast smile",
     2: "2 - crop + fast smile + fast binning",
     3: "3 - crop + fast smile + slow binning",
     4: "4 - crop + fast smile + fast binning + conversion to radiance in units of uW/cm^2/sr/nm"
}

# Initialize the camera at startup with explicit parameters.
cam = openhsiCamera(
    img_path='assets/great_hall_slide.png',
    n_lines=1024,
    exposure_ms=1, 
    processing_lvl=-1, 
    json_path="assets/cam_settings.json",
    cal_path="assets/cam_calibration.nc"
)

# Global flags and lock for capture status.
collection_running = False
capture_finished = False
collection_lock = threading.Lock()

def run_collection():
    global collection_running, capture_finished
    with collection_lock:
        collection_running = True
        capture_finished = False  # Clear finished flag at start.
    try:
        # This call blocks until capture completes.
        cam.collect()
    finally:
        with collection_lock:
            collection_running = False
            capture_finished = True  # Set finished flag when done.

@app.route('/')
def index():
    # Generate form fields HTML from the settings.
    form_fields = ""
    for key in ["n_lines", "exposure_ms", "processing_lvl"]:
        if key == "processing_lvl":
            current_value = cam.settings.get(key, "")
            form_fields += f'<div class="form-group"><label for="{key}">{key}:</label>'
            form_fields += f'<select id="{key}" name="{key}" class="form-control setting">'
            for option_value, option_desc in PROCESSING_LVL_OPTIONS.items():
                try:
                    selected = "selected" if int(current_value) == option_value else ""
                except (ValueError, TypeError):
                    selected = ""
                form_fields += f'<option value="{option_value}" {selected}>{option_desc}</option>'
            form_fields += '</select></div>'
        else:
            value = cam.settings.get(key, "")
            form_fields += (
                f'<div class="form-group"><label for="{key}">{key}:</label>'
                f'<input type="text" id="{key}" name="{key}" class="form-control setting" value="{value}">'
                f'</div>'
            )
    # Render the index.html template and pass the form_fields.
    return render_template("index.html", form_fields=form_fields)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    new_settings = request.get_json()
    try:
        # Convert n_lines to an integer.
        if "n_lines" in new_settings:
            new_settings["n_lines"] = int(new_settings["n_lines"])
        # Convert exposure_ms to a float.
        if "exposure_ms" in new_settings:
            new_exposure = float(new_settings["exposure_ms"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        # Update exposure using the set_exposure method.
        if "exposure_ms" in new_settings:
            cam.set_exposure(new_exposure)
        # Update n_lines via reinitialisation.
        if "n_lines" in new_settings:
            cam.reinitialise(n_lines=new_settings["n_lines"])
        # Update processing level.
        if "processing_lvl" in new_settings:
            new_pl = int(new_settings["processing_lvl"])
            cam.reinitialise(processing_lvl=new_pl)
        # Reset capture flag after settings change.
        with collection_lock:
            global capture_finished
            capture_finished = False
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/capture', methods=['POST'])
def capture():
    global collection_running
    with collection_lock:
        if collection_running:
            return jsonify({"status": "Capture already in progress"}), 200
        thread = threading.Thread(target=run_collection)
        thread.start()
    return jsonify({"status": "Capture started"})

@app.route('/save', methods=['POST'])
def save_files():
    data = request.get_json()
    save_dir = data.get("save_dir", "data")
    try:
        cam.save(save_dir=save_dir)
        return jsonify({"status": "success", "message": f"Files saved to {save_dir}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    with collection_lock:
        return jsonify({"capturing": collection_running, "finished": capture_finished})

@app.route('/show', methods=['GET'])
def show_image():
    # If a capture has not been completed, return a 204 No Content response.
    with collection_lock:
        if not capture_finished:
            return '', 204    
    # Otherwise, generate the image as usual.
    try:
        # Generate the figure using cam.show.
        fig = cam.show(plot_lib="matplotlib", hist_eq=False, robust=True)
    except Exception as e:
        # If there's an error generating the figure, also return 204.
        return '', 204
    
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
        temp_filename = tmpfile.name
    try:
        hv.save(fig, temp_filename, fmt='png')
        with open(temp_filename, 'rb') as f:
            img_data = f.read()
        buf = BytesIO(img_data)
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    finally:
        os.remove(temp_filename)

# New endpoints for browsing directories recursively.
@app.route('/browse/', defaults={'subpath': ''})
@app.route('/browse/<path:subpath>')
def browse(subpath):
    base_dir = "data"
    current_dir = os.path.join(base_dir, subpath)
    # Ensure the current_dir is within base_dir to prevent directory traversal
    if not os.path.abspath(current_dir).startswith(os.path.abspath(base_dir)):
        abort(403)
    if not os.path.isdir(current_dir):
        abort(404)
    try:
        items = os.listdir(current_dir)
    except Exception as e:
        items = []
    dirs = []
    files = []
    for item in items:
        full_path = os.path.join(current_dir, item)
        if os.path.isdir(full_path):
            dirs.append(item)
        else:
            files.append(item)
    # Build HTML list with navigation links.
    html = "<!doctype html><html><head><title>Browse Files</title><style>h1 { color: #2A7AE2; }</style></head><body>"
    html += f"<h1>Browsing: /{subpath}</h1>" if subpath else "<h1>Browsing: /data</h1>"
    if subpath:
        parent = os.path.dirname(subpath)
        html += f'<p><a href="/browse/{parent}">[Parent Directory]</a></p>'
    html += "<ul>"
    for d in sorted(dirs):
        new_subpath = os.path.join(subpath, d)
        html += f'<li>[DIR] <a href="/browse/{new_subpath}">{d}</a></li>'
    for f in sorted(files):
        new_path = os.path.join(subpath, f)
        html += f'<li>[FILE] <a href="/download/{new_path}">{f}</a></li>'
    html += "</ul>"
    html += '<p><a href="/">Return to main page</a></p>'
    html += "</body></html>"
    return html

# Updated download endpoint to support subdirectories.
@app.route('/download/<path:filename>')
def download(filename):
    data_dir = "data"
    # This will send the file as an attachment.
    return send_from_directory(data_dir, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=False, threaded=True)