# GNSS positioning with RTKlib
By Filippo Gavuglio and Tommaso Viotti

## Goals

The goal of our project is to use the RTKlib software on a Raspberry Pi 4, together with an antenna equipped with a u-blox receiver, in order to build a positioning system capable of achieving centimeter-level accuracy while using low-end hardware.

## Used Technologies

### RTKlib Explorer
RTKlib is a software package developed by researcher Tomoji Takasu at the Tokyo University of Marine Science and Technology. However, for our project we used a specific branch (RTKlib-EX) developed by Tim Everett, which provides improved performance on low- to mid-range devices: https://github.com/rtklibexplorer/RTKLIB

### InfluxDB
As for the database component, we used InfluxDB (https://docs.influxdata.com/influxdb3/core/), since its Python library is well suited for time-series use cases, such as ours.

## Files

### Main_controller.py
The software’s entry point is responsible for implementing the following pipeline:
1. It opens an SSH connection to the Raspberry Pi.
2. Upload, Through SSH, the rtklib config file on the Raspberry
3. Through SSH, it starts the RTKlib instance.
4. It launches the server_rtk.py script.
5. It launches the live_plotter.py script.
6. It remains in a listening state and shuts down all processes upon receiving an interrupt command.

### Server_rtk.py
This script is responsible for establishing a connection with the RTKlib instance running on the Raspberry Pi (via a TCP socket), starting the database core, and handling all RTKlib outputs in order to parse them and perform queries on the database table.

### Live_plotter.py
This script is responsible for establishing a connection to the database, performing queries, and plotting the data on a map in order to visualize the rover’s position.


