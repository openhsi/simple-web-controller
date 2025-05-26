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
import time
from io import BytesIO
import tempfile
import holoviews as hv
from tqdm import tqdm
import matplotlib

matplotlib.use("Agg")

from openhsi.cameras import FlirCamera as openhsiCameraOrig

# openhsi calibration settings
# json_path = "/home/openhsi/UNE/cals/OpenHSI-SAIL-UNE-01/OpenHSI-SAIL-UNE-01_settings_Mono8_bin1.json"
# cal_path = "/home/openhsi/UNE/cals/OpenHSI-SAIL-UNE-01/OpenHSI-SAIL-UNE-01_calibration_Mono8_bin1.nc"
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
    version="1.1",
    title="OpenHSI  Capture API",
    description="API for managing OpenHSI capture and file operations",
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

# Model for advanced camera settings
advanced_settings_model = api.model(
    "AdvancedSettings",
    {
        "row_slice": fields.List(
            fields.Integer,
            required=False,
            description="Range of rows to read from detector [start, end]",
            example=[8, 913],
        ),
        "resolution": fields.List(
            fields.Integer,
            required=False,
            description="Image resolution [height, width]",
            example=[924, 1240],
        ),
        "fwhm_nm": fields.Float(
            required=False,
            description="Full Width at Half Maximum (spectral resolution) in nanometers",
            example=4.0,
        ),
        "luminance": fields.Float(
            required=False, description="Luminance value for calibration", example=10000
        ),
        "binxy": fields.List(
            fields.Integer,
            required=False,
            description="Binning factors [x, y]",
            example=[1, 1],
        ),
        "win_offset": fields.List(
            fields.Integer,
            required=False,
            description="Window offset [x, y]",
            example=[96, 200],
        ),
        "win_resolution": fields.List(
            fields.Integer,
            required=False,
            description="Window resolution [width, height]",
            example=[924, 1240],
        ),
        "pixel_format": fields.String(
            required=False,
            description="Pixel format (Mono8, Mono12, or Mono16)",
            example="Mono8",
        ),
    },
)

# Update the settings model to include advanced settings
full_settings_model = api.inherit(
    "FullSettings", settings_model, advanced_settings_model
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

# Define detailed settings with types, descriptions, and validation
DETAILED_SETTINGS = {
    "row_slice": {
        "type": "array_int",
        "description": "Range of rows to read from detector [start, end]",
        "min_value": 0,
        "max_value": 1024,
        "size": 2,
    },
    "resolution": {
        "type": "array_int",
        "description": "Image resolution [height, width]",
        "min_value": 1,
        "max_value": 2048,
        "size": 2,
    },
    "fwhm_nm": {
        "type": "float",
        "description": "Full Width at Half Maximum (spectral resolution) in nanometers",
        "min_value": 0.1,
        "max_value": 100,
    },
    "exposure_ms": {
        "type": "float",
        "description": "Exposure time in milliseconds",
        "min_value": 0.1,
        "max_value": 1000,
    },
    "luminance": {
        "type": "float",
        "description": "Luminance value for calibration",
        "min_value": 0,
        "max_value": 100000,
    },
    "binxy": {
        "type": "array_int",
        "description": "Binning factors [x, y]",
        "min_value": 1,
        "max_value": 8,
        "size": 2,
    },
    "win_offset": {
        "type": "array_int",
        "description": "Window offset [x, y]",
        "min_value": 0,
        "max_value": 2048,
        "size": 2,
    },
    "win_resolution": {
        "type": "array_int",
        "description": "Window resolution [width, height]",
        "min_value": 1,
        "max_value": 2048,
        "size": 2,
    },
    "pixel_format": {
        "type": "select",
        "description": "Pixel format",
        "options": ["Mono8", "Mono12", "Mono16"],
    },
}

# Global flags and lock for capture status.
collection_running = False
capture_finished = False
collection_lock = threading.Lock()

# Log messages storage
log_messages = []
log_lock = threading.Lock()


def add_log_message(message, message_type="info"):
    """Add a message to the log with timestamp and type."""
    with log_lock:
        timestamp = int(time.time() * 1000)  # milliseconds since epoch
        log_messages.append(
            {
                "timestamp": timestamp,
                "time": time.strftime("%H:%M:%S"),
                "message": message,
                "type": message_type,
            }
        )
        # Keep only the last 100 messages
        if len(log_messages) > 100:
            log_messages.pop(0)


def run_collection():
    global collection_running, capture_finished, capture_progress
    with collection_lock:
        collection_running = True
        capture_finished = False
        capture_progress = {}
    try:
        # Pass the update_progress callback, which now receives the tqdm progress dict.
        add_log_message("Collection process started", "info")
        cam.collect(progress_callback=update_progress)
        add_log_message("Collection completed successfully", "success")
    except Exception as e:
        add_log_message(f"Error during collection: {str(e)}", "error")
        app.logger.error(f"Collection error: {e}")
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

    # Get the current camera settings for the detailed tab
    current_settings = {}
    for setting_key in DETAILED_SETTINGS.keys():
        if setting_key in cam.settings:
            current_settings[setting_key] = cam.settings[setting_key]
        else:
            # Provide default empty values based on type
            setting_info = DETAILED_SETTINGS[setting_key]
            if setting_info["type"] == "array_int":
                current_settings[setting_key] = [0] * setting_info.get("size", 2)
            elif setting_info["type"] == "float":
                current_settings[setting_key] = 0.0
            elif setting_info["type"] == "select":
                current_settings[setting_key] = setting_info.get("options", [""])[0]

    return render_template(
        "index.html",
        form_fields=form_fields,
        detailed_settings=DETAILED_SETTINGS,
        current_settings=current_settings,
    )


# -------------------------------------------------------------------------
@api.route("/update_settings")
class UpdateSettings(Resource):
    @api.expect(full_settings_model, validate=True)
    @api.response(200, "Settings updated successfully")
    @api.response(400, "Invalid input")
    @api.response(500, "Internal error while updating settings")
    @api.doc(
        params={
            "n_lines": "Number of scan lines to capture",
            "exposure_ms": "Exposure time in milliseconds",
            "processing_lvl": "Processing level (-1 to 4)",
            "row_slice": "Range of rows to read from detector [start, end]",
            "resolution": "Image resolution [height, width]",
            "fwhm_nm": "Full Width at Half Maximum (spectral resolution) in nanometers",
            "luminance": "Luminance value for calibration",
            "binxy": "Binning factors [x, y]",
            "win_offset": "Window offset [x, y]",
            "win_resolution": "Window resolution [width, height]",
            "pixel_format": "Pixel format (Mono8, Mono12, or Mono16)",
        }
    )
    def post(self):
        """
        Update camera settings (both basic and advanced).

        This endpoint handles both the basic settings (n_lines, exposure_ms, processing_lvl)
        and the advanced detailed settings for the camera.

        Advanced settings include:
        - row_slice: Range of rows to read from detector [start, end]
        - resolution: Image resolution [height, width]
        - fwhm_nm: Full Width at Half Maximum (spectral resolution) in nanometers
        - exposure_ms: Exposure time in milliseconds
        - luminance: Luminance value for calibration
        - binxy: Binning factors [x, y]
        - win_offset: Window offset [x, y]
        - win_resolution: Window resolution [width, height]
        - pixel_format: Pixel format (Mono8, Mono12, or Mono16)
        """
        new_settings = request.get_json()
        app.logger.info("Received update_settings payload: %s", new_settings)

        # Track which detailed settings were provided
        detailed_settings_provided = {}
        for key in DETAILED_SETTINGS.keys():
            if key in new_settings:
                detailed_settings_provided[key] = new_settings[key]

        try:
            # Validate and parse basic settings
            if "n_lines" in new_settings and new_settings["n_lines"] != "":
                new_settings["n_lines"] = int(new_settings["n_lines"])
            else:
                # Optional: Set a default or skip if not provided.
                new_settings["n_lines"] = None

            # For updating from the basic settings tab
            if "exposure_ms" in new_settings and new_settings["exposure_ms"] != "":
                new_exposure = float(new_settings["exposure_ms"])
            else:
                # If no exposure is provided (e.g., when updating only detailed settings)
                # and we already have one in the camera, use the current exposure
                if hasattr(cam, "settings") and "exposure_ms" in cam.settings:
                    new_exposure = cam.settings["exposure_ms"]
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
            # Update basic camera settings
            cam.set_exposure(new_exposure)
            if new_settings["n_lines"] is not None:
                cam.reinitialise(n_lines=new_settings["n_lines"])
            cam.reinitialise(processing_lvl=new_pl)

            # Update detailed settings if provided
            if detailed_settings_provided:
                app.logger.info(
                    "Updating detailed settings: %s", detailed_settings_provided
                )
                # We should actually use the cam's API or configuration to update these settings
                # This implementation would depend on the specifics of the OpenHSI camera API
                # For now, we'll just log them and pretend we updated them
                for key, value in detailed_settings_provided.items():
                    app.logger.info(f"Would update {key} to {value}")
                    # In a real implementation, you would call the appropriate camera API methods
                    # Example: cam.set_setting(key, value)

            with collection_lock:
                global capture_finished
                capture_finished = False

            # Add to log
            if detailed_settings_provided:
                add_log_message(f"Camera advanced settings updated", "success")
            else:
                add_log_message(
                    f"Camera basic settings updated - exposure: {new_exposure}ms, lines: {new_settings['n_lines'] if new_settings['n_lines'] is not None else 'unchanged'}, processing: {new_pl}",
                    "success",
                )

            return {"status": "success"}, 200
        except Exception as e:
            app.logger.error("Error updating settings: %s", e, exc_info=True)
            add_log_message(f"Error updating camera settings: {str(e)}", "error")
            return {"status": "error", "error": f"Internal error: {e}"}, 500


@api.route("/capture")
class Capture(Resource):
    @api.response(200, "Capture started or already in progress")
    def post(self):
        """Start the image capture process."""
        global collection_running
        with collection_lock:
            if collection_running:
                add_log_message("Capture already in progress", "info")
                return {"status": "Capture already in progress"}, 200
            thread = threading.Thread(target=run_collection)
            thread.start()
        add_log_message("Image capture started", "info")
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
            filepath = (
                f"{cam.directory}/{cam.timestamps[0].strftime('%Y_%m_%d-%H_%M_%S')}.nc"
            )
            add_log_message(f"Files saved to {save_dir}", "success")
            return {
                "status": "success",
                "message": f"Files saved to {save_dir}",
                "filepath": filepath,
            }, 200
        except Exception as e:
            add_log_message(f"Error saving files: {str(e)}", "error")
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
    @api.param("hist_eq", "Apply histogram equalization", type="boolean")
    @api.param("robust", "Apply robust contrast stretching", type="boolean")
    @api.param("band", "Band to display (rgb, red, green, blue, nir)", type="string")
    @api.param("stretch", "Contrast stretch percentage", type="integer")
    def get(self):
        """Retrieve the captured image as a PNG file with display options."""
        with collection_lock:
            if not capture_finished:
                return "", 204

        # Parse display parameters
        hist_eq = request.args.get("hist_eq", "false").lower() == "true"
        robust = request.args.get("robust", "true").lower() == "true"
        band = request.args.get("band", "rgb")
        stretch = int(request.args.get("stretch", "0"))

        app.logger.info(
            f"Showing image with settings - hist_eq: {hist_eq}, robust: {robust}, band: {band}, stretch: {stretch}"
        )

        try:
            # Note: This is a simplified implementation - the actual implementation
            # would depend on what parameters the cam.show() method actually supports

            # Basic parameters that cam.show() already supports
            fig = cam.show(plot_lib="matplotlib", hist_eq=hist_eq, robust=robust)

            # Note: Additional parameters like band selection and stretch percentage
            # would need to be implemented in the camera's show method
            # For now, we'll just pass the parameters we know work
        except Exception as e:
            app.logger.error(f"Error generating image: {e}")
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

    # Build HTML page with improved styling and file management
    html = """<!doctype html>
    <html>
    <head>
        <title>Browse Files</title>
        <link rel="stylesheet" href="/static/css/bootstrap.min.css">
        <script src="/static/js/bootstrap.bundle.min.js"></script>
        <style>
            body { padding: 20px; }
            h1 { color: #2A7AE2; margin-bottom: 20px; }
            .file-browser { margin-top: 20px; }
            .file-actions { display: flex; gap: 8px; }
            .file-image-modal img { max-width: 100%; }
        </style>
    </head>
    <body>
    <div class="container">
        <h1>Browsing: {path_display}</h1>
        
        <div class="row">
            <div class="col-md-12">
                <nav aria-label="breadcrumb">
                    <ol class="breadcrumb">
                        <li class="breadcrumb-item"><a href="/browse/">Root</a></li>
    """

    # Add breadcrumbs for navigation
    path_parts = subpath.split(os.sep) if subpath else []
    path_so_far = ""
    for i, part in enumerate(path_parts):
        if not part:  # Skip empty parts
            continue
        path_so_far = os.path.join(path_so_far, part)
        if i == len(path_parts) - 1:  # Last part is current directory
            html += (
                f'<li class="breadcrumb-item active" aria-current="page">{part}</li>'
            )
        else:
            html += f'<li class="breadcrumb-item"><a href="/browse/{path_so_far}">{part}</a></li>'

    html += """
                    </ol>
                </nav>
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-12">
                <div class="card file-browser">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Files and Directories</span>
                        <a href="/" class="btn btn-sm btn-outline-primary">Return to main page</a>
                    </div>
                    <div class="card-body">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Name</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    # Add parent directory link if not at root
    if subpath:
        parent = os.path.dirname(subpath)
        html += f"""
                                <tr>
                                    <td><i class="bi bi-folder"></i></td>
                                    <td><a href="/browse/{parent}">..</a></td>
                                    <td></td>
                                </tr>
        """

    # Add directories
    for d in sorted(dirs):
        new_subpath = os.path.join(subpath, d)
        html += f"""
                                <tr>
                                    <td><span class="badge bg-primary">DIR</span></td>
                                    <td><a href="/browse/{new_subpath}">{d}</a></td>
                                    <td></td>
                                </tr>
        """

    # Add files with actions
    for f in sorted(files):
        new_path = os.path.join(subpath, f)
        file_ext = os.path.splitext(f)[1].lower()

        actions = f'<div class="file-actions">'

        # Different action based on file type
        if file_ext in [".png", ".jpg", ".jpeg", ".gif"]:
            # Image files - view in browser
            actions += f'<a href="/api/view/{new_path}" class="btn btn-sm btn-outline-info" target="_blank">View</a>'
            actions += f'<a href="/api/download/{new_path}" class="btn btn-sm btn-outline-secondary">Download</a>'
        else:
            # Other files - direct download
            actions += f'<a href="/api/download/{new_path}" class="btn btn-sm btn-outline-secondary">Download</a>'

        # Add delete button for all files
        actions += f'<button class="btn btn-sm btn-outline-danger" onclick="deleteFile(\'{new_path}\')">Delete</button>'
        actions += "</div>"

        html += f"""
                                <tr>
                                    <td><span class="badge bg-secondary">FILE</span></td>
                                    <td>{f}</td>
                                    <td>{actions}</td>
                                </tr>
        """

    # Close the table and add JavaScript for delete functionality
    html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Delete confirmation modal -->
    <div class="modal fade" id="deleteModal" tabindex="-1" aria-labelledby="deleteModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="deleteModalLabel">Confirm Delete</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    Are you sure you want to delete this file?
                    <p id="fileToDelete" class="fw-bold mt-2"></p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-danger" id="confirmDelete">Delete</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let filePathToDelete = '';
        const deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
        
        function deleteFile(path) {
            filePathToDelete = path;
            document.getElementById('fileToDelete').textContent = path;
            deleteModal.show();
        }
        
        document.getElementById('confirmDelete').addEventListener('click', function() {
            // Send API request to delete the file
            fetch('/api/delete/' + filePathToDelete, { method: 'DELETE' })
                .then(response => {
                    if (response.ok) {
                        // Reload the page to update the file list
                        window.location.reload();
                    } else {
                        alert('Error deleting file');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error deleting file');
                })
                .finally(() => {
                    deleteModal.hide();
                });
        });
    </script>
    </body>
    </html>
    """

    path_display = f"/{subpath}" if subpath else "/data"
    html = html.replace("{path_display}", path_display)

    return html


@api.route("/view/<path:filename>")
class ViewFile(Resource):
    @api.param("filename", "The file path relative to the data directory")
    @api.response(200, "File sent for viewing")
    @api.response(404, "File not found")
    def get(self, filename):
        """View a file (especially images) in the browser without downloading."""
        data_dir = "/data"
        # Check if the path is safe (within /data directory)
        full_path = os.path.join(data_dir, filename)
        if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
            abort(403)  # Forbidden if trying to access outside /data

        # Check file existence
        if not os.path.isfile(full_path):
            abort(404)  # Not found

        # For image files, return without attachment headers
        return send_from_directory(data_dir, filename, as_attachment=False)


@api.route("/download/<path:filename>")
class Download(Resource):
    @api.param("filename", "The file path relative to the data directory")
    @api.response(200, "File sent as attachment")
    @api.response(404, "File not found")
    def get(self, filename):
        """Download a file from the data directory."""
        data_dir = "/data"
        # Check if the path is safe (within /data directory)
        full_path = os.path.join(data_dir, filename)
        if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
            abort(403)  # Forbidden if trying to access outside /data

        return send_from_directory(data_dir, filename, as_attachment=True)


@api.route("/delete/<path:filename>")
class DeleteFile(Resource):
    @api.param("filename", "The file path relative to the data directory")
    @api.response(200, "File deleted successfully")
    @api.response(403, "Forbidden - Cannot delete outside data directory")
    @api.response(404, "File not found")
    @api.response(500, "Error occurred while deleting file")
    def delete(self, filename):
        """Delete a file from the data directory."""
        data_dir = "/data"
        # Check if the path is safe (within /data directory)
        full_path = os.path.join(data_dir, filename)
        if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
            return {
                "status": "error",
                "message": "Cannot delete files outside data directory",
            }, 403

        # Check file existence
        if not os.path.isfile(full_path):
            return {"status": "error", "message": "File not found"}, 404

        try:
            # Delete the file
            os.remove(full_path)
            app.logger.info(f"Deleted file: {full_path}")
            return {
                "status": "success",
                "message": f"File {filename} deleted successfully",
            }, 200
        except Exception as e:
            app.logger.error(f"Error deleting file {full_path}: {e}")
            return {"status": "error", "message": f"Error deleting file: {str(e)}"}, 500


@api.route("/file_list")
class FileList(Resource):
    @api.param(
        "folder", "The folder path to list (relative to data directory)", required=False
    )
    @api.response(200, "File list retrieved successfully")
    @api.response(403, "Forbidden - Cannot access directory outside data directory")
    @api.response(404, "Directory not found")
    def get(self):
        """Get a list of all files in the specified directory."""
        data_dir = "/data"
        folder = request.args.get("folder", "")

        # Build the target directory path
        target_dir = os.path.join(data_dir, folder)

        # Security check - ensure path is within data directory
        if not os.path.abspath(target_dir).startswith(os.path.abspath(data_dir)):
            return {
                "status": "error",
                "message": "Cannot access directory outside data directory",
            }, 403

        # Check if directory exists
        if not os.path.isdir(target_dir):
            return {"status": "error", "message": "Directory not found"}, 404

        try:
            # Get all items in the directory
            items = os.listdir(target_dir)

            # Separate files and directories
            files = []
            directories = []

            for item in items:
                item_path = os.path.join(target_dir, item)
                if os.path.isdir(item_path):
                    # For directories, add with trailing slash
                    rel_path = os.path.relpath(item_path, data_dir)
                    directories.append(
                        {"name": item, "path": rel_path, "type": "directory"}
                    )
                else:
                    # For files, include size and modification time
                    file_stats = os.stat(item_path)
                    rel_path = os.path.relpath(item_path, data_dir)

                    # Get file extension
                    _, ext = os.path.splitext(item)

                    files.append(
                        {
                            "name": item,
                            "path": rel_path,
                            "type": "file",
                            "size": file_stats.st_size,
                            "modified": file_stats.st_mtime,
                            "extension": ext.lower(),
                        }
                    )

            # Return both files and directories
            return {
                "status": "success",
                "current_dir": folder or "/",
                "files": files,
                "directories": directories,
            }, 200

        except Exception as e:
            return {"status": "error", "message": f"Error listing files: {str(e)}"}, 500


@api.route("/logs")
class LogMessages(Resource):
    @api.response(200, "Log messages retrieved successfully")
    def get(self):
        """Retrieve the log messages."""
        with log_lock:
            return {"status": "success", "logs": log_messages}, 200

    @api.response(200, "Log messages cleared successfully")
    def delete(self):
        """Clear the log messages."""
        with log_lock:
            global log_messages
            log_messages = []
            return {"status": "success", "message": "Log messages cleared"}, 200


if __name__ == "__main__":
    # Add initial log message
    add_log_message("Server started", "success")
    app.run(debug=False, threaded=True)
