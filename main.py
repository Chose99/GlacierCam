'''GlacierCam firmware - see https://github.com/Eagleshot/GlacierCam for more information'''

from io import BytesIO
from os import system, remove, listdir, path
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from picamera2 import Picamera2
from libcamera import controls
from yaml import safe_load, safe_dump
import suntime
from sim7600x import SIM7600X
from witty_pi_4 import WittyPi4
from fileserver import FileServer
from settings import Settings

###########################
# Configuration and filenames
###########################

# Get unique hardware id of Raspberry Pi
# See: https://www.raspberrypi.com/documentation/computers/config_txt.html#the-serial-number-filter
# and https://raspberrypi.stackexchange.com/questions/2086/how-do-i-get-the-serial-number
def get_cpu_serial():
    '''Get the unique serial number of Raspberry Pi CPU'''
    cpuserial = "0000000000000000"
    try:
        with open('/proc/cpuinfo', 'r', encoding='utf-8') as f:
            for cpu_line in f:
                if cpu_line[0:6] == 'Serial':
                    cpuserial = cpu_line[10:26]
                    break
    except:
        cpuserial = "ERROR000000000"

    return cpuserial

FILE_PATH = "/home/pi/"  # Path where files are saved

# Error logging
LOG_LEVEL = logging.WARNING
file_handler = RotatingFileHandler(f"{FILE_PATH}log.txt", mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.basicConfig(level=LOG_LEVEL, handlers=[file_handler, stream_handler])

# Read config.yaml file from SD card
try:
    with open(f"{FILE_PATH}config.yaml", 'r', encoding='utf-8') as file:
        config = safe_load(file)
except Exception as e:
    logging.critical("Could not open config.yaml: %s", str(e))

CAMERA_NAME = get_cpu_serial() # Unique hardware serial number
TIMESTAMP_CSV = datetime.today().strftime('%Y-%m-%d %H:%MZ') # UTC-Time
TIMESTAMP_FILENAME = datetime.today().strftime('%Y%m%d_%H%MZ') # UTC-Time

data = {'timestamp': TIMESTAMP_CSV}

###########################
# Connect to fileserver
###########################

fileserver = FileServer(config["ftpServerAddress"], config["username"], config["password"])
CONNECTED_TO_SERVER = fileserver.connected()

# Go to custom directory on fileserver if specified
try:
    # Custom directory
    if config["ftpDirectory"] != "" and CONNECTED_TO_SERVER:
        fileserver.change_directory(config["ftpDirectory"], True)

    # Custom camera directory
    if config["multipleCamerasOnServer"] and CONNECTED_TO_SERVER:
        fileserver.change_directory(CAMERA_NAME, True)
except Exception as e:
    logging.warning("Could not change directory on fileserver: %s", str(e))

###########################
# Settings
###########################

# Try to download settings from server
try:
    if CONNECTED_TO_SERVER:

        file_list = fileserver.list_files()

        # Check if settings file exists
        if "settings.yaml" in file_list:
            fileserver.download_file("settings.yaml", FILE_PATH)
        else:
            logging.warning("No settings file on server. Creating new file with default settings.")
            fileserver.upload_file("settings.yaml", FILE_PATH)
except Exception as e:
    logging.critical("Could not download settings file from FTP server: %s", str(e))

# Read settings file
try:
    settings = Settings(f"{FILE_PATH}settings.yaml")
except Exception as e:
    logging.critical("Could not open settings.yaml: %s", str(e))

###########################
# Time synchronization
###########################

try:
    wittyPi = WittyPi4()

    if settings.get("timeSync") and CONNECTED_TO_SERVER:
        wittyPi.sync_time_with_network()
except Exception as e:
    logging.warning("Could not synchronize time with network: %s", str(e))

###########################
# Schedule script
###########################

# Get sunrise and sunset times
try:
    if settings.get("enableSunriseSunset") and settings.get("latitude") != 0 and settings.get("longitude") != 0:
        sun = suntime.Sun(settings.get("latitude"), settings.get("longitude"))

        # Sunrise
        sunrise = sun.get_sunrise_time()
        logging.info("Next sunrise: %s:%s", sunrise.hour, sunrise.minute)
        sunrise = WittyPi4.round_time_to_nearest_interval(sunrise, settings.get("intervalMinutes"))
        settings.set("startTimeHour", sunrise.hour)
        settings.set("startTimeMinute", sunrise.minute)

        # Sunset
        sunset = sun.get_sunset_time()
        logging.info("Next sunset: %s:%s", sunset.hour, sunset.minute)
        repetitions_per_day = WittyPi4.calculate_num_repetitions_per_day(sunrise, sunset, settings.get("intervalMinutes"))
        settings.set("repetitionsPerday", repetitions_per_day)

except Exception as e:
    logging.warning("Could not get sunrise and sunset times: %s", str(e))

try:
    battery_voltage = wittyPi.get_battery_voltage()
    data["battery_voltage"] = battery_voltage

    battery_voltage_half = settings.get("battery_voltage_half")
    battery_voltage_quarter = (battery_voltage_half-settings.get("low_voltage_threshold"))*0.5

    if battery_voltage_quarter < battery_voltage < battery_voltage_half: # Battery voltage between 50% and 25%
        settings.set("intervalMinutes", int(settings.get("intervalMinutes")*2))
        settings.set("repetitionsPerday", int(settings.get("repetitionsPerday")/2))
        logging.warning("Battery voltage <50%.")
    elif battery_voltage < battery_voltage_quarter: # Battery voltage <25%
        settings.set("repetitionsPerday", 1)
        logging.warning("Battery voltage <25%.")

except Exception as e:
    logging.warning("Could not get battery voltage: %s", str(e))

###########################
# Generate schedule
###########################
try:
    start_time_hour = settings.get("startTimeHour")
    start_time_minute = settings.get("startTimeMinute")
    interval_minutes = settings.get("intervalMinutes")
    repetitions_per_day = settings.get("repetitionsPerday")
    wittyPi.generate_schedule(start_time_hour, start_time_minute, interval_minutes, repetitions_per_day)
except Exception as e:
    wittyPi.generate_schedule(8, 0, 30, 8)
    logging.warning("Failed to generate schedule: %s", str(e))

###########################
# Apply schedule
###########################
try:
    next_startup_time = wittyPi.apply_schedule()
    data['next_startup_time'] = f"{next_startup_time}Z"
except Exception as e:
    logging.critical("Could not apply schedule: %s", str(e))

##########################
# SIM7600G-H 4G module
###########################

# See Waveshare documentation
try:
    sim7600 = SIM7600X()
except Exception as e:
    logging.warning("Could not open serial connection with 4G module: %s", str(e))

# Enable GPS
try:
    # Enable GPS to later read out position
    if settings.get("enableGPS"):
        sim7600.start_gps_session()
except Exception as e:
    logging.warning("Could not start GPS: %s", str(e))

###########################
# Setup camera
###########################
try:
    camera = Picamera2()
    cameraConfig = camera.create_still_configuration() # Selects highest resolution by default

    # https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
    # Table 6. Stream- specific configuration parameters
    MIN_RESOLUTION = 64
    MAX_RESOLUTION = (4608, 2592)
    resolution = settings.get("resolution")

    if MIN_RESOLUTION < resolution[0] < MAX_RESOLUTION[0] and MIN_RESOLUTION < resolution[1] < MAX_RESOLUTION[1]:
        size = (resolution[0], resolution[1])
        cameraConfig = camera.create_still_configuration({"size": size})

except Exception as e:
    logging.critical("Could not setup camera: %s", str(e))

# Focus settings
try:
    if settings.get("lensPosition") > -1:
        camera.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": settings.get("lensPosition")})
    else:
        camera.set_controls({"AfMode": controls.AfModeEnum.Auto})
except Exception as e:
    logging.warning("Could not set lens position: %s", str(e))

###########################
# Capture image
###########################
try:
    image_filename = f'{TIMESTAMP_FILENAME}.jpg'
    if settings.get("cameraName") != "":
        image_filename = f'{TIMESTAMP_FILENAME}_{settings.get("cameraName")}.jpg'
except Exception as e:
    logging.warning("Could not set custom camera name: %s", str(e))

try:
    camera.start_and_capture_file(FILE_PATH + image_filename, capture_mode=cameraConfig, delay=2, show_preview=False)
except Exception as e:
    logging.critical("Could not start camera and capture image: %s", str(e))

###########################
# Stop camera
###########################
try:
    camera.stop()
except Exception as e:
    logging.warning("Could not stop camera: %s", str(e))

###########################
# Upload image(s) to file server
###########################

try:
    if CONNECTED_TO_SERVER:
        # Upload all images
        for file in listdir(FILE_PATH):
            if file.endswith(".jpg"):
                fileserver.upload_file(file, FILE_PATH)

                # Delete uploaded image from Raspberry Pi
                remove(FILE_PATH + file)
except Exception as e:
    logging.critical("Could not upload image to fileserver: %s", str(e))

###########################
# Set voltage thresholds
###########################
try:
    # If settings low voltage threshold exists
    if settings.get("low_voltage_threshold"):
        wittyPi.set_low_voltage_threshold(settings.get("low_voltage_threshold"))

    # If settings recovery voltage threshold exists
    if settings.get("recovery_voltage_threshold"):
        # Recovery voltage threshold must be equal or greater than low voltage threshold
        if settings.get("recovery_voltage_threshold") < settings.get("low_voltage_threshold"):
            settings.set("recovery_voltage_threshold", settings.get("low_voltage_threshold"))

        wittyPi.set_recovery_voltage_threshold(settings.get("recovery_voltage_threshold"))

except Exception as e:
    logging.warning("Could not set voltage thresholds: %s", str(e))

###########################
# Get readings
###########################
try:
    data["temperature"] = wittyPi.get_temperature()
    data["internal_voltage"] = wittyPi.get_internal_voltage()
    # data["internal_current"] = wittyPi.get_internal_current()
    data["signal_quality"] = sim7600.get_signal_quality()
except Exception as e:
    logging.warning("Could not get readings: %s", str(e))

###########################
# Get GPS position
###########################
try:
    if settings.get("enableGPS"):
        data["latitude"], data["longitude"], data["height"] = sim7600.get_gps_position()
        sim7600.stop_gps_session()

except Exception as e:
    logging.warning("Could not get GPS coordinates: %s", str(e))

###########################
# Uploading sensor data to server
###########################

# Append new measurements to log or create new log file if none exists
try:
    DIAGNOSTICS_FILENAME = "diagnostics.yaml"
    diagnostics_filepath = f"{FILE_PATH}{DIAGNOSTICS_FILENAME}"

    # Check if is connected to file server
    if CONNECTED_TO_SERVER:
        try:
            # Check if local diagnostics file exists
            if path.exists(diagnostics_filepath):
                with open(diagnostics_filepath, 'r', encoding='utf-8') as yaml_file:
                    read_data = safe_load(yaml_file)

                data = read_data + [data]

                remove(diagnostics_filepath)
        except Exception as e:
            logging.warning("Could not open diagnostics file: %s", str(e))


        # Upload diagnostics to server
        byte_stream = BytesIO()
        safe_dump([data], stream=byte_stream, default_flow_style=False, encoding='utf-8')
        byte_stream.seek(0)  # Set the position to the beginning of the BytesIO object
        fileserver.append_file_from_bytes(DIAGNOSTICS_FILENAME, byte_stream)
    else:
        # Append new measurement to local YAML file
        with open(diagnostics_filepath, 'a', encoding='utf-8') as yaml_file:
            safe_dump([data], yaml_file, default_flow_style=False)
except Exception as e:
    logging.warning("Could not append new measurements to log: %s", str(e))

###########################
# Upload diagnostics data
###########################
try:
    fileserver.append_file("log.txt", FILE_PATH)

    # Upload WittyPi diagnostics
    if settings.get("uploadWittyPiDiagnostics") and CONNECTED_TO_SERVER:
        fileserver.append_file("wittyPi.log", f"{FILE_PATH}wittypi/")
        fileserver.append_file("schedule.log", f"{FILE_PATH}wittypi/")
except Exception as e:
    logging.warning("Could not upload diagnostics data: %s", str(e))

###########################
# Quit file server session
###########################
try:
    if CONNECTED_TO_SERVER:
        fileserver.quit()
except Exception as e:
    logging.warning("Could not close file server session: %s", str(e))

###########################
# Shutdown Raspberry Pi if enabled
###########################
try:
    if settings.get("shutdown") or settings.get("shutdown") is None:
        logging.info("Shutting down now.")
        system("sudo shutdown -h now")
except Exception as e:
    system("sudo shutdown -h now")
