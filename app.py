import os
import subprocess
import io
import sys
import hashlib
import logging
from flask import Flask, request, send_file, render_template, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(levelname)s %(message)s"
)

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')

# Folders and paths
UPLOAD_FOLDER = 'uploads'
GBA_ROM_FOLDER = '/gba'
NDS_ROM_FOLDER = '/nds'
GBC_ROM_FOLDER = "/gbc"
PRESET_FOLDER = os.path.join('randomizer', 'presets')
JAR_PATH = os.path.join('randomizer', 'PokeRandoZX.jar')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Number of bytes to use for checksum calculation (1 MB)
HASH_BYTES = 1048576

# Mapping from game codes to (family, game name, preset options)
GAME_PRESETS = {
    # GBA Games
    "BPRE": ("FRLG", "FireRed", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "BPGE": ("FRLG", "LeafGreen", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "AXVE": ("RSE", "Ruby", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "AXPE": ("RSE", "Sapphire", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "BPEE": ("RSE", "Emerald", ["Thor","Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    # NDS Games
    "CPUE": ("DPP", "Diamond", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "CPUJ": ("DPP", "Pearl", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "CPUP": ("DPP", "Platinum", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "IPKE": ("HGSS", "HeartGold", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    "IPGE": ("HGSS", "SoulSilver", ["Standard", "Ultimate", "Kaizo", "Survival", "SuperKaizo"]),
    # GBC (Crystal)
    "CRYSTAL": ("GSC", "Crystal", ["Standard", "Kaizo", "Survival"]),
}

def compute_file_checksum(filepath, hash_bytes=HASH_BYTES):
    """Compute the SHA-256 hash of the first hash_bytes of a file (or the entire file if smaller)."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            data = f.read(hash_bytes)
            hasher.update(data)
        checksum = hasher.hexdigest()
        app.logger.info(f"Server: Checksum of {checksum}")
        return checksum
    except Exception as e:
        app.logger.error(f"Error computing checksum: {e}")
        raise

def identify_game(filepath):
    """
    Identify the game from the ROM file.
    Reads known header offsets for GBA, NDS, and GBC to determine the game code or title.
    """
    try:
        with open(filepath, 'rb') as rom:
            # GBA: game code at offset 0xAC (4 bytes)
            rom.seek(0xAC)
            gba_code = rom.read(4).decode('ascii', errors='ignore')
            # NDS: game code at offset 0x0C (4 bytes)
            rom.seek(0x0C)
            nds_code = rom.read(4).decode('ascii', errors='ignore')
            # GBC: title at offset 0x134 (16 bytes) to detect Crystal
            rom.seek(0x134)
            gbc_title = rom.read(16).decode('ascii', errors='ignore').strip()
    except Exception:
        app.logger.error(f"Error reading ROM file {filepath}")
        return None, None, None
    
    if "CRYSTAL" in gbc_title.upper():
        return GAME_PRESETS.get("CRYSTAL")
    if gba_code in GAME_PRESETS:
        app.logger.info(f"Identified ROM with GBA code: {gba_code}")
        return GAME_PRESETS[gba_code]
    if nds_code in GAME_PRESETS:
        app.logger.info(f"Identified ROM with NDS code: {nds_code}")
        return GAME_PRESETS[nds_code]
    
    return None, None, None

roms = ["Select a Rom"]
@app.route('/')
def index():
    return render_template('index.html',roms=roms)

@app.route('/check_rom', methods=['POST'])
def check_rom():
    """
    Check whether a ROM file (identified by checksum and extension) already exists.
    Expects JSON with 'checksum' and 'ext'.
    """
    data = request.get_json()
    checksum = data.get('checksum')
    ext = data.get('ext')
    if not checksum or not ext:
        return jsonify({"error": "Missing checksum or extension"}), 400
    stored_filename = f"{checksum}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, stored_filename)
    exists = os.path.exists(file_path)
    app.logger.info(f"Client: Checksum of {ext} file: {checksum}")
    return jsonify({"exists": exists, "stored_filename": stored_filename})

@app.route('/upload_rom', methods=['POST'])
def upload_rom():
    """
    Upload a new ROM file.
    Expects form-data with 'checksum', 'ext', and 'romfile'.
    After saving, the server verifies that the file’s checksum matches the provided value.
    """
    if 'romfile' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    checksum = request.form.get('checksum')
    ext = request.form.get('ext')
    if not checksum or not ext:
        return jsonify({"error": "Missing checksum or extension"}), 400
    
    file = request.files['romfile']
    stored_filename = f"{checksum}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, stored_filename)
    
    # Save only if the file doesn't already exist
    if not os.path.exists(file_path):
        file.save(file_path)
        app.logger.info(f"Uploaded file is new")
    else:
        app.logger.info(f"Uploaded file already exists")
    
    # Verify the checksum on the server side
    computed_checksum = compute_file_checksum(file_path)
    if computed_checksum != checksum:
        app.logger.error(f"Checksum mismatch for {stored_filename}")
        os.remove(file_path)
        return jsonify({"error": "Checksum mismatch"}), 400
    
    return jsonify({"success": True, "stored_filename": stored_filename})

@app.route('/get_presets', methods=['POST'])
def get_presets():
    """
    Identify the ROM and return the available presets.
    Expects JSON with 'stored_filename'.
    """
    data = request.get_json()
    stored_filename = data.get('stored_filename')
    if not stored_filename:
        return jsonify({"error": "Missing stored_filename"}), 400
    file_path = os.path.join(UPLOAD_FOLDER, stored_filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    _, game, presets = identify_game(file_path)
    if not game:
        os.remove(file_path)
        return jsonify({"error": "Unrecognized ROM file"}), 400
    app.logger.info(f"Identified game: {game} with presets: {presets}")
    return jsonify({"game": game, "presets": presets})

@app.route('/randomize', methods=['POST'])
def randomize():
    """
    Randomize the ROM using the chosen preset.
    Expects form-data with 'stored_filename' and 'preset'.
    """
    stored_filename = request.form.get('stored_filename')
    preset = request.form.get('preset')
    if not stored_filename or not preset:
        return jsonify({"error": "Missing parameters"}), 400
    
    input_filepath = os.path.join(UPLOAD_FOLDER, stored_filename)
    if not os.path.exists(input_filepath):
        return jsonify({"error": "ROM file not found"}), 404
    
    family, game, presets = identify_game(input_filepath)
    if not game:
        return jsonify({"error": "Unsupported ROM file"}), 400
    
    if preset not in presets:
        return jsonify({"error": "Invalid preset selection"}), 400
    
    # Locate the preset file (for example: FRLG_Standard.rnqs)
    preset_file = os.path.join(PRESET_FOLDER, f"{family}_{preset}.rnqs")
    if not os.path.exists(preset_file):
        return jsonify({"error": f"Preset file {preset_file} not found"}), 500
    
    # Create an output filename based on the game and preset
    ext = os.path.splitext(stored_filename)[1]
    output_filename = f"{game}_{preset}{ext}"
    output_filepath = os.path.join(UPLOAD_FOLDER, output_filename)
    
    command = [
        "java", "-Xmx512M", "-jar", JAR_PATH, "cli",
        "-s", preset_file,
        "-i", input_filepath,
        "-o", output_filepath
    ]
    
    try:
        app.logger.info(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        return jsonify({"error": "Randomization failed",
                        "details": e.stderr.decode() or e.stdout.decode()}), 500
    
    return jsonify({"success": True, "download_url": f"/download/{output_filename}"})

@app.route('/download/<filename>')
def download_file(filename):
    """
    Serve the randomized file for download and delete it immediately after sending.
    """
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    with open(file_path, "rb") as f:
        file_data = io.BytesIO(f.read())
    os.remove(file_path)
    file_data.seek(0)
    return send_file(file_data, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    for rom_path in [GBA_ROM_FOLDER,GBC_ROM_FOLDER,NDS_ROM_FOLDER]:
        if os.path.exists(rom_path):
            app.logger.info(f"Found ROM Path: {rom_path}")
            for x in os.listdir(rom_path):
                if "pokemon" in x.lower() and (x.endswith(".gba") or x.endswith(".gb") or x.endswith(".nds")):
                    if identify_game(os.path.join(rom_path, x))[0] is not None:
                        app.logger.info(f"Identified ROM: {x}")
                        roms.append(os.path.join(rom_path, x))
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=False)
