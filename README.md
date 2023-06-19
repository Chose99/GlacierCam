# GlacierCam
## Installation
### 1. Install Raspberry Pi OS
Required hardware: microSD card, computer with microSD card reader and internet connection

Download and install the Raspberry Pi Imager to flash the OS to the microSD card. The software can be downloaded [here](https://www.raspberrypi.com/software/).

Open the raspberry Pi Imager and click on the "Choose OS" button. Select "Raspberry Pi OS (other)" and click on "CHOOSE OS". Select "Raspberry Pi OS Lite (32-bit)" (the Pi Zero is a 32-bit computer). Then insert the microSD card and select it in the "SD Card" menu. Next click on the gear icon and select "Set Username and Password" and set a unique username and password. You can also add a WiFi connection if you don't have an ethernet adapter. In addition you can change the keyboard layout and timezone.

Then click on "SAVE" and "WRITE" to flash the OS to the microSD card. This process will take roughly 15 minutes, depending on the speed of the microSD card and the internet connection. When the process is finished, remove the microSD card from the computer and insert it into the Raspberry Pi. Attention: This will delete all data on the microSD card.

### Setup the software on the Raspberry Pi
Required hardware: Raspberry Pi Zero WH (or other), monitor, HDMI to microHDMI adapter (optional), keyboard (with micro usb to usb adapter), power supply, ethernet adapter or WiFi for Pi Zero W

Insert the microSD card and connect the Raspberry Pi to the monitor, keyboard, mouse and power supply. Boot up the Raspberry Pi and wait until it has started up. It may reboot several times. Log in with the username and password you set up in the previous step. The default username is "pi" and the default password is "raspberry".

 write the following command in the terminal:

```bash
wget -O - https://raw.githubusercontent.com/Eagleshot/GlacierCam/main/script.sh | sudo sh
```


## Update the software 
To update the main.py file only, run the following command in the terminal:

```bash
sudo wget -O /home/pi/main.py https://raw.githubusercontent.com/Eagleshot/GlacierCam/main/main.py
```

## Modifying Raspberry Pi OS
### Modify config.txt
Speed up boot time by disabling unneeded services
See: https://himeshp.blogspot.com/2018/08/fast-boot-with-raspberry-pi.html


Edit the config.txt file:
```bash
sudo nano /boot/config.txt
```
Add/modify the following lines:
```bash
boot_delay=0 # Set the boot delay to 0 seconds
disable_splash=1 # Disable the splash screen
dtparam=act_led_trigger=none # Disable the LED

dtoverlay=disable-bt # Disable bluetooth
dtoverlay=disable-wifi # Disable wifi # TODO

```

### Modify cmdline.txt
Edit the cmdline.txt file:
```bash
sudo nano /boot/cmdline.txt
```
Add/modify the following lines:
```bash
quiet
```
This will disable the boot messages.

# Check services and their impact on boot time
```bash
systemd-analyze blame
systemd-analyze critical-chain
```
Returns a list of services and their boot time impact.

# Disable services
Disable dhcpcd.service. Caution, this will break the internet connection if upload is done over bluetooth or ethernet.
```bash

Turn off white LED of witty pi

# TODOs
- [ ] Witty Pi timing script -> replace /wittypi/script.sh
- [ ] Set focus in settings.py
- [ ] Sync time with NTP server / witty pi
- [ ] Get real error messages from the camera
- [ ] USB Backup
- [ ] Web interface of ftp server (streamlit)
- [ ] Camera Compression and metadata
- [ ] Yaml instead of settings.py