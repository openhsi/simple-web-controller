from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_file,
    send_from_directory,
    abort,
    Blueprint,
)
from flask_restx import Api, Resource, fields
import threading
import os
from io import BytesIO
import tempfile
import holoviews as hv
from tqdm import tqdm
import matplotlib

matplotlib.use("Agg")

from openhsi.cameras import FlirCamera as openhsiCameraOrig

# openhsi calibration settings
json_path = "/home/openhsi/orlar/cals/OpenHSI-SAIL-orlar-01/OpenHSI-SAIL-orlar-01_settings_Mono8_bin1.json"
cal_path = "/home/openhsi/orlar/cals/OpenHSI-SAIL-orlar-01/OpenHSI-SAIL-orlar-01_calibration_Mono8_bin1.nc"


# reimplemnted openhsi capture to allow capture progress feedback.
class openhsiCamera(openhsiCameraOrig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def collect(self, progress_callback=None):
        self.start_cam()
        pbar = tqdm(range(self.n_lines))
        for _ in pbar:
            self.put(self.get_img())
            if callable(getattr(self, "get_temp", None)):
                self.cam_temperatures.put(self.get_temp())
            # If a progress_callback is provided, extract the progress data from pbar.
            if progress_callback:
                # pbar.format_dict returns a dictionary with useful keys
                # such as 'n', 'total', 'elapsed', and 'eta'.
                progress_callback(pbar.format_dict)
        self.stop_cam()


# Initialize the camera at startup with explicit parameters.
cam = openhsiCamera(
    n_lines=512,
    exposure_ms=10,
    processing_lvl=-1,
    json_path=json_path,
    cal_path=cal_path,
)

app = Flask(__name__)

# Create a blueprint for the API with a URL prefix (e.g. '/api')
api_bp = Blueprint("api", __name__, url_prefix="/api")
api = Api(
    api_bp,
    version="1.0",
    title="Camera Capture API",
    description="API for managing camera capture and file operations",
    doc="/apidocs",
    swagger_ui_parameters={"docExpansion": "full"},
)  # Swagger UI will be at /api/apidocs

# Register the blueprint with the main Flask app.
app.register_blueprint(api_bp)

# Define models for the API requests.
settings_model = api.model(
    "Settings",
    {
        "n_lines": fields.Integer(
            required=False, description="Number of lines", example=512
        ),
        "exposure_ms": fields.Float(
            required=False, description="Exposure time in milliseconds", example=10.0
        ),
        "processing_lvl": fields.Integer(
            required=False, description="Processing level", example=-1
        ),
    },
)

save_model = api.model(
    "Save",
    {
        "save_dir": fields.String(
            required=False,
            description="Directory where files will be saved",
            example="/data",
        )
    },
)

# Define the list of settings to show.
SETTING_KEYS = ["n_lines", "exposure_ms", "processing_lvl"]

# Allowed processing levels with updated descriptions.
PROCESSING_LVL_OPTIONS = {
    -1: "-1 - do not apply any transforms (default)",
    0: "0 - crop to useable sensor area",
    1: "1 - crop + fast smile",
    2: "2 - crop + fast smile + fast binning",
    3: "3 - crop + fast smile + slow binning",
    4: "4 - crop + fast smile + fast binning + conversion to radiance in units of uW/cm^2/sr/nm",
}

# Global flags and lock for capture status.
collection_running = False
capture_finished = False
collection_lock = threading.Lock()


def run_collection():
    global collection_running, capture_finished, capture_progress
    with collection_lock:
        collection_running = True
        capture_finished = False
        capture_progress = {}
    try:
        # Pass the update_progress callback, which now receives the tqdm progress dict.
        cam.collect(progress_callback=update_progress)
    finally:
        with collection_lock:
            collection_running = False
            capture_finished = True


# Global variable to store progress info.
capture_progress = {}


def update_progress(progress_info):
    global capture_progress
    # Extract desired values from progress_info.
    current = progress_info.get("n", 0)
    total = progress_info.get("total", 0)
    elapsed = progress_info.get("elapsed", 0)
    rate = progress_info.get("rate", 0)
    percentage = (current / total) * 100 if total else 0
    capture_progress = {
        "current": current,
        "total": total,
        "elapsed": elapsed,
        "rate": rate,
        "percentage": percentage,
    }


# -------------------------------------------------------------------------
# Non-API route: Render the main index page with a settings form.
@app.route("/")
def index():
    # Generate form fields HTML from the settings.
    form_fields = ""
    for key in SETTING_KEYS:
        if key == "processing_lvl":
            current_value = cam.settings.get(key, "")
            form_fields += f'<div class="form-group"><label for="{key}">{key}:</label>'
            form_fields += (
                f'<select id="{key}" name="{key}" class="form-control setting">'
            )
            for option_value, option_desc in PROCESSING_LVL_OPTIONS.items():
                try:
                    selected = "selected" if int(current_value) == option_value else ""
                except (ValueError, TypeError):
                    selected = ""
                form_fields += (
                    f'<option value="{option_value}" {selected}>{option_desc}</option>'
                )
            form_fields += "</select></div>"
        else:
            value = cam.settings.get(key, "")
            form_fields += (
                f'<div class="form-group"><label for="{key}">{key}:</label>'
                f'<input type="text" id="{key}" name="{key}" class="form-control setting" value="{value}">'
                f"</div>"
            )
    return render_template("index.html", form_fields=form_fields)


# -------------------------------------------------------------------------
@api.route("/update_settings")
class UpdateSettings(Resource):
    @api.expect(settings_model, validate=True)
    @api.response(200, "Settings updated successfully")
    @api.response(400, "Invalid input")
    @api.response(500, "Internal error while updating settings")
    def post(self):
        """Update the camera settings."""
        new_settings = request.get_json()
        try:
            app.logger.info("Received update_settings payload: %s", new_settings)
            # Validate and parse inputs.
            if "n_lines" in new_settings and new_settings["n_lines"] != "":
                new_settings["n_lines"] = int(new_settings["n_lines"])
            else:
                # Optional: Set a default or skip if not provided.
                new_settings["n_lines"] = None

            if "exposure_ms" in new_settings and new_settings["exposure_ms"] != "":
                new_exposure = float(new_settings["exposure_ms"])
            else:
                raise ValueError(
                    "Exposure time (exposure_ms) is required and must be a number."
                )

            if (
                "processing_lvl" in new_settings
                and new_settings["processing_lvl"] != ""
            ):
                new_pl = int(new_settings["processing_lvl"])
            else:
                # Default processing level if not provided.
                new_pl = -1
        except Exception as e:
            app.logger.error("Error parsing input: %s", e, exc_info=True)
            return {"status": "error", "error": f"Input error: {e}"}, 400

        try:
            # Update camera settings.
            cam.set_exposure(new_exposure)
            if new_settings["n_lines"] is not None:
                cam.reinitialise(n_lines=new_settings["n_lines"])
            cam.reinitialise(processing_lvl=new_pl)
            with collection_lock:
                global capture_finished
                capture_finished = False
            return {"status": "success"}, 200
        except Exception as e:
            app.logger.error("Error updating settings: %s", e, exc_info=True)
            return {"status": "error", "error": f"Internal error: {e}"}, 500


@api.route("/capture")
class Capture(Resource):
    @api.response(200, "Capture started or already in progress")
    def post(self):
        """Start the image capture process."""
        global collection_running
        with collection_lock:
            if collection_running:
                return {"status": "Capture already in progress"}, 200
            thread = threading.Thread(target=run_collection)
            thread.start()
        return {"status": "Capture started"}, 200


@api.route("/save")
class SaveFiles(Resource):
    @api.expect(save_model, validate=True)
    @api.response(200, "Files saved successfully")
    @api.response(500, "Error occurred while saving files")
    def post(self):
        """Save the captured files to a specified directory."""
        data = request.get_json()
        save_dir = data.get("save_dir", "/data")
        try:
            cam.save(save_dir=save_dir)
            return {"status": "success", "message": f"Files saved to {save_dir}"}, 200
        except Exception as e:
            api.abort(500, str(e))


@api.route("/status")
class Status(Resource):
    @api.response(200, "Status retrieved successfully")
    def get(self):
        """Retrieve the current capture status along with progress details."""
        with collection_lock:
            return {
                "capturing": collection_running,
                "finished": capture_finished,
                "progress": capture_progress,
            }, 200


@api.route("/show")
class ShowImage(Resource):
    @api.response(200, "Image retrieved successfully")
    @api.response(204, "No Content – capture not finished or image generation error")
    def get(self):
        """Retrieve the captured image as a PNG file."""
        with collection_lock:
            if not capture_finished:
                return "", 204
        try:
            fig = cam.show(plot_lib="matplotlib", hist_eq=False, robust=False)
        except Exception:
            return "", 204

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            temp_filename = tmpfile.name
        try:
            hv.save(fig, temp_filename, fmt="png")
            with open(temp_filename, "rb") as f:
                img_data = f.read()
            buf = BytesIO(img_data)
            buf.seek(0)
            return send_file(buf, mimetype="image/png")
        finally:
            os.remove(temp_filename)


# New endpoints for browsing directories recursively.
@app.route("/browse/", defaults={"subpath": ""})
@app.route("/browse/<path:subpath>")
def browse(subpath):
    """
    Browse directories recursively in the data folder.
    ---
    tags:
      - Files
    parameters:
      - name: subpath
        in: path
        required: false
        description: The subdirectory path relative to the base data directory.
        schema:
          type: string
          example: "folder/subfolder"
    responses:
      200:
        description: HTML page listing directories and files.
        content:
          text/html:
            schema:
              type: string
      403:
        description: Forbidden - Attempt to access an unauthorized directory.
      404:
        description: Not Found - The specified directory does not exist.
    """
    base_dir = "/data"
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
        html += f'<li>[FILE] <a href="/api/download/{new_path}">{f}</a></li>'
    html += "</ul>"
    html += '<p><a href="/">Return to main page</a></p>'
    html += "</body></html>"
    return html


@api.route("/download/<path:filename>")
class Download(Resource):
    @api.param("filename", "The file path relative to the data directory")
    @api.response(200, "File sent as attachment")
    @api.response(404, "File not found")
    def get(self, filename):
        """Download a file from the data directory."""
        data_dir = "/data"
        return send_from_directory(data_dir, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=False, threaded=True)
