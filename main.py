#!/usr/bin/python3
# -*- coding:utf-8 -*-

# TODO Fix upload settings.yaml

# Import required libraries
from picamera2 import Picamera2
from libcamera import controls
from ftplib import FTP
from datetime import datetime
from time import sleep
from csv import writer
from os import system, remove
from io import BytesIO, StringIO
from subprocess import check_output, STDOUT
import yaml

###########################
# Filenames
###########################
# Get unique hardware id of Raspberry Pi
# See: https://www.raspberrypi.com/documentation/computers/config_txt.html#the-serial-number-filter
# and https://raspberrypi.stackexchange.com/questions/2086/how-do-i-get-the-serial-number
def getCPUSerial():
    # Extract serial from cpuinfo file
    cpuserial = "0000000000000000"
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line[0:6] == 'Serial':
                    cpuserial = line[10:26]
                    break
    except:
        cpuserial = "ERROR000000000"

    return cpuserial
 
cpuSerial = getCPUSerial()

with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

with open("settings.yaml", 'r') as file:
    settings = yaml.safe_load(file)

cameraName = config['cameraName'] # Camera name
folderName = cameraName + "_" + cpuSerial # Camera folder with camera name + unique hardware serial
imgFileName = datetime.today().strftime('%d%m%Y_%H%M_') + cameraName + "_" + cpuSerial + ".jpg"
imgFilePath = "/home/pi/"  # Path where image is saved

###########################
# Readings
###########################
csvFileName = "diagnostics.csv"
currentTime = datetime.today().strftime('%d-%m-%Y %H:%M')
currentTemperature = ""
currentBatteryVoltage = "" 
raspberryPiVoltage = ""
currentPowerDraw = ""
currentSignalQuality = ""
currentGPSPosLat = "-"
currentGPSPosLong = "-"
error = "" #TODO Real error messages

###########################
# SIM7600X
###########################
# See Waveshare documentation
try:
    import serial
    ser = serial.Serial('/dev/ttyUSB2', 115200)  # USB connection
    ser.flushInput()
except Exception as e:
    error += "Could not open serial connection with 4G module: " + str(e)
    print ("Could not open serial connection with 4G module: " + str(e))

power_key = 6
rec_buff = ''
rec_buff2 = ''
time_count = 0

def send_at2(command, back, timeout):
    rec_buff = ''
    ser.write((command+'\r\n').encode())
    sleep(timeout)
    if ser.inWaiting():
        sleep(0.01)
        rec_buff = ser.read(ser.inWaiting())
    if back not in rec_buff.decode():
        print(command + ' ERROR')
        print(command + ' back:\t' + rec_buff.decode())
        return 0
    else:
        return rec_buff.decode()

# Get GPS Position
def send_at(command, back, timeout):
    rec_buff = ''
    ser.write((command+'\r\n').encode())
    sleep(timeout)
    if ser.inWaiting():
        sleep(0.01)
        rec_buff = ser.read(ser.inWaiting())
    if rec_buff != '':
        if back not in rec_buff.decode():
            print(command + ' ERROR')
            print(command + ' back:\t' + rec_buff.decode())
            return 0
        elif ',,,,,,' in rec_buff.decode():
            print('GPS is not ready')
            return 0
        else:
            # Additions to Demo Code Written by Tim! -> Core Electronics
            GPSDATA = str(rec_buff.decode())
            Cleaned = GPSDATA[13:]
            # print(Cleaned)

            Lat = Cleaned[:2]
            SmallLat = Cleaned[2:11]
            NorthOrSouth = Cleaned[12]
            # print(Lat, SmallLat, NorthOrSouth)

            Long = Cleaned[14:17]
            SmallLong = Cleaned[17:26]
            EastOrWest = Cleaned[27]
            # print(Long, SmallLong, EastOrWest)

            FinalLat = float(Lat) + (float(SmallLat)/60)
            FinalLong = float(Long) + (float(SmallLong)/60)

            if NorthOrSouth == 'S':
                FinalLat = -FinalLat
            if EastOrWest == 'W':
                FinalLong = -FinalLong

            FinalLongText = round(FinalLong, 7)
            FinalLatText = round(FinalLat, 7)

            global currentGPSPosLat
            global currentGPSPosLong
            currentGPSPosLat = str(FinalLatText)
            currentGPSPosLong = str(FinalLongText)

            print('Longitude:' + currentGPSPosLong +
                  ' Degrees - Latitude: ' + currentGPSPosLat + ' Degrees')

            return 1
    else:
        print('GPS is not ready')
        return 0

###########################
# Setup camera
###########################
camera = Picamera2()
cameraConfig = camera.create_still_configuration() # Automatically selects the highest resolution possible

# TODO If -1 set to autofocus
try:
    camera.set_controls({"AfMode": controls.AfModeEnum.Manual,
                        "LensPosition": settings["lensPosition"]})
except Exception as e:
    error += "Could not set lens position: " + str(e)
    print("Could not set lens position: " + str(e))

###########################
# Capture image
###########################
try:
    camera.start_and_capture_file(
        imgFilePath + imgFileName, capture_mode=cameraConfig, delay=3, show_preview=False)
except Exception as e:
    error += "Could not start camera and capture image: " + str(e)
    print("Could not start camera and capture image: " + str(e))

###########################
# Stop camera
###########################
try:
    camera.stop()
except Exception as e:
    error += "Camera already stopped. "
    print("Camera already stopped.")

###########################
# Upload picture to server
###########################
ftp = FTP(config["ftpServerAddress"], timeout=120)
ftp.login(user=config["username"], passwd=config["password"])

# Go to folder with camera name + unique hardware serial number or create it
try:
    ftp.cwd(folderName)
except:
    ftp.mkd(folderName)
    ftp.cwd(folderName)

###########################
# Upload to ftp server and then delete last image
###########################
try:
    with open(imgFilePath + imgFileName, 'rb') as file:
        ftp.storbinary(f"STOR {imgFileName}", file)
        print(f"Successfully uploaded {imgFileName}")

    # Delete last image
    remove(imgFilePath + imgFileName)

except Exception as e:
    error += "Could not open image. " + str(e)
    print("Could not open image. " + str(e))

###########################
# Uploading sensor data to CSV
###########################

# Get WittyPi readings
try:

    # https://www.baeldung.com/linux/run-function-in-script

    # Temperature
    command = "cd /home/pi/wittypi && . ./utilities.sh && get_temperature"
    currentTemperature = check_output(command, shell=True, executable="/bin/bash", stderr=STDOUT, universal_newlines=True)
    currentTemperature = currentTemperature.replace("\n", "")
    currentTemperature = currentTemperature.split(" / ")[0] # Remove the Farenheit reading
    print("Temperature: " + currentTemperature)

    # Battery voltage
    command = "cd /home/pi/wittypi && . ./utilities.sh && get_input_voltage"
    currentBatteryVoltage = check_output(command, shell=True, executable="/bin/bash", stderr=STDOUT, universal_newlines=True) + "V"
    currentBatteryVoltage = currentBatteryVoltage.replace("\n", "")
    print("Battery voltage: " + currentBatteryVoltage)

    # Raspberry Pi voltage
    command = "cd /home/pi/wittypi && . ./utilities.sh && get_output_voltage"
    raspberryPiVoltage = check_output(command, shell=True, executable="/bin/bash", stderr=STDOUT, universal_newlines=True) + "V"
    raspberryPiVoltage = raspberryPiVoltage.replace("\n", "")
    print("Output voltage: " + raspberryPiVoltage)

    # Current Power Draw (@5V)
    command = "cd /home/pi/wittypi && . ./utilities.sh && get_output_current"
    currentPowerDraw = check_output(command, shell=True, executable="/bin/bash", stderr=subprocess.STDOUT, universal_newlines=True) + "A"
    currentPowerDraw = currentPowerDraw.replace("\n", "")
    print("Output current: " + currentPowerDraw)

except Exception as e:
    error += "Failed to get WittyPi readings: " + str(e)
    print("Failed to get WittyPi readings: " + str(e))

# Get GPS position
# SIM7600X-Module is already turned on
try:
    if settings["enableGPS"]  == True:
        answer = 0
        print('Start GPS session.')
        rec_buff = ''
        send_at('AT+CGPS=1,1', 'OK', 1)
        sleep(2)
        maxAttempts = 0

        while (maxAttempts <= 35):
            maxAttempts += 1
            answer = send_at('AT+CGPSINFO', '+CGPSINFO: ', 1)
            if answer == 1:  # Success
                break
            else:
                print('error %d' % answer)
                send_at('AT+CGPS=0', 'OK', 1)
                sleep(1.5)
except:
    error += "Failed to get GPS coordinates. "
    print("Failed to get GPS coordinates.")

# Get cell signal quality
try:
    currentSignalQuality = send_at2('AT+CSQ', 'OK', 1)[8:13]
    currentSignalQuality = currentSignalQuality.replace("\n", "")
    print("Cell signal quality: " + currentSignalQuality)
except:
    error += "Failed to get cell signal quality. "
    print("Failed to get cell signal quality.")

# Upload data to server
newRow = [currentTime, currentBatteryVoltage, raspberryPiVoltage, currentPowerDraw, currentTemperature, currentSignalQuality, currentGPSPosLat, currentGPSPosLong, error]

# Append new measurements to log CSV or create new CSV file if none exists
with StringIO() as csvBuffer:
    writer = writer(csvBuffer)
    writer.writerow(newRow)
    csvData = csvBuffer.getvalue().encode('utf-8')
    ftp.storbinary(f"APPE {csvFileName}", BytesIO(csvData))

###########################
# Download and read config file -> TODO work with read only file system
###########################
try:
    with open('/home/pi/settings.py', 'wb') as fp:  # Download
        ftp.retrbinary('RETR settings.py', fp.write)
except Exception as e:
    print('No config file found. Creating new config file with default settings: ' + str(e))

    # Upload config file if none exists
    with open('/home/pi/settings.py', 'rb') as fp:  # Download
        ftp.storbinary('STOR settings.py', fp)

try:
    ftp.quit
except:
    print('Could not quit FTP session.')

# Shutdown computer if defined in loop
if settings["shutdown"] == True:
    print('Shutting down now.')
    system("sudo shutdown -h now")
