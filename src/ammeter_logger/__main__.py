from .ammeter_recv import AmmeterRecvSerial
from .logging_handler import create_logger
import argparse
from time import sleep, time
import json
import csv
from datetime import datetime
import signal

def write_log_data(serial_device:AmmeterRecvSerial, args:dict):
    """ Write the log data to the specified file """
    print(f"Writing log to file {args['file']}...")
    with open(args['file'], 'w', encoding='utf-8') as output_file:
        writer = csv.writer(output_file)
        header = ['received_epoch', 'name', 'received_datetime', 'ticks', 'latest']
        for x in range(len(serial_device.ammeter_data[0]['last_reads'])):
            header.append(f'read_{x+1}')
        header.append('time_from_start')
        header.append('average')
        writer.writerow(header)
        for record in serial_device.ammeter_data:
            row = [
                record['received'], 
                record['name'],  
                datetime.fromtimestamp(record['received']).strftime('%Y-%m-%d %H:%M:%S.%f'),
                record['ticks'], 
                record['current_amps']]
            for x in range(len(record['last_reads'])):
                row.append(record['last_reads'][x])
            row.append(float(record['ticks'])/1000)
            row.append(record['average'])
            writer.writerow(row)
    print("Writing complete.")


if __name__ == '__main__':
    # setup the argument parser
    parser = argparse.ArgumentParser(description="Start the ammeter data collector.  Requires the sender to be running (provided sender is Micropython for a microcontroller)")
    parser.add_argument('device', metavar='DEVICE', help='Serial device connected to the microcontroller (i.e. /dev/ttyUSB0')
    parser.add_argument('file', metavar='OUTPUT_FILE', help='File to save captured data to')
    parser.add_argument('--get-config', dest='get_config', required=False, action='store_true', default=False, help="(False) Get the configuration from the microcontroller and quit")
    parser.add_argument('--get-status', dest='get_status', required=False, action='store_true', default=False, help="(False) Get the current status of the microcontroller and quit")
    parser.add_argument('--skip-init', dest='skip_init', required=False, action='store_true', default=False, help="(False) Skip initializing the ammeter (not recommended!)")
    parser.add_argument('--force-init', dest='force_init', required=False, action='store_true', default=False, help="(False) Force init of the ammeter")
    parser.add_argument('--init-only', dest='init_only', required=False, action='store_true', default=False, help="(False) Only initalize the ammeter, print the config and status and quit (implies --force-init)")
    parser.add_argument('--sample-interval', dest='sample_interval', required=False, type=int, default=0, help="Set the sampling interval, overrides the config on the microcontroller")
    parser.add_argument('--capture-time', dest='capture_time', required=False, type=int, default=None, help="Set the max time to capture before stopping, overrides the config on the microcontroller")
    parser.add_argument('--baudrate', dest='baudrate', required=False, type=int, default=115200, help="(115200) Set the baudrate for the serial interface")
    parser.add_argument('--log-level', dest='log_level', required=False, type=str, default='INFO', help='(INFO) Specify the logging level for the console')

    args = vars(parser.parse_args())

    # Create the device
    serial_device = AmmeterRecvSerial(args['device'], baudrate=args['baudrate'], logger=create_logger(console=True, console_level=args['log_level']))

    # get config and status if requested and quit
    if args['get_config']:
        print(f"Current Config: {serial_device.ammeter_config}")
        if not args['get_status']:
            quit()
    if args['get_status']:
        print(f"Current Status: {serial_device.ammeter_status}")
        quit()

    # initialize the device
    if (not serial_device.ammeter_initialized and not args['skip_init']) or args['force_init'] or args['init_only']:
        serial_device.ammeter_init()
        timeout = time() + 2 + serial_device.ammeter_config['init_timeout']
        while time() < timeout:
            status = serial_device.ammeter_status
            if status['status'] != 'READY' or status['status'] != 'RUNNING':
                print(f'Waiting for ammeter to initialize. {status}')
            else:
                break
            sleep(2)
        if not serial_device.ammeter_ready:
            print(f"Ammeter is not ready!  Current status: {serial_device.ammeter_status}")
            quit(1)
    if args['init_only']:
        print(f"Current Config: {serial_device.ammeter_config}")
        print(f"Current Status: {serial_device.ammeter_status}")
        quit()

    # start the logging
    return_value = serial_device.ammeter_start(timeout=args['capture_time'])
    if not return_value:
        print(f"Error starting the ammeter!  Current status: {serial_device.ammeter_status}")
        quit()
    
    # Configure a handler to catch a Ctrl+C
    def break_handler(signum, frame):
        """ Handle a ctrl+c from the user to stop the data collection and write the collected data """
        print(f"Caught Ctrl+C.  Stopping data collection...")
        if serial_device.ammeter_stop():
            write_log_data(serial_device, args)
        else:
            print(f"Error stopping the ammeter!  Current status: {serial_device.ammeter_status}")
        quit()
    signal.signal(signal.SIGINT, break_handler)

    # wait for the logging to complete
    print(f"Starting data collection.  Collection will run for {serial_device.ammeter_config['timeout']} seconds.  You can stop at any point and write the captured data using CTRL+C.")
    timeout = time() + 2 + (serial_device.ammeter_config['timeout'] if args['capture_time'] is None else args['capture_time'])
    while time() < timeout:
        status = serial_device.ammeter_status
        if status['status'] == 'RUNNING':
            last_read = serial_device.ammeter_data[len(serial_device.ammeter_data) - 1]['average'] if len(serial_device.ammeter_data) > 0 else 0
            print(f"Waiting for logging run to complete.  Last amp read: {last_read}.  Current status: {status}")
        elif status['status'] == 'READY':
            print(f"Logging Run complete.  Current status: {status}.  Captured {len(serial_device.ammeter_data)} intervals")
            break
        else:
            print(f"Microcontroller reporting an unexpected state: {status}.  Check and try again.")
            quit(1)
        sleep(2)
    
    # logging complete, write the data to a file
    write_log_data(serial_device, args)