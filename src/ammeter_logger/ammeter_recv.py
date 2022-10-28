"""
Class to open and read serial data from the Micropython ammeter
"""
import serial
import logging
from time import sleep, time
from threading import Thread, Lock
from ast import literal_eval


class AmmeterRecvSerial(serial.Serial):
    """ Class to open and read serial data from the Micropython ammeter - overrides the py-serial class """
    def __init__(self, *args, **kwargs):
        self._logger = kwargs.get('logger', logging)
        kwargs.pop('logger')
        super().__init__(*args, **kwargs)
        self.ammeter_data = []
        self.ammeter_partial_data = ''
        self.ammeter_data_lock = Lock()
        self.ammeter_config_lock = Lock()
        self.ammeter_status_lock = Lock()
        self.ammeter_config_data = {}
        self.ammeter_status_data = {}
        self._ammeter_recv_thread = Thread(target=self._ammeter_read, daemon=True)
        self._ammeter_recv_thread.start()

    @property
    def _info_str(self):
        """ Returns a string identifying the class for logging purposes """
        return f"{self.__class__.__name__}: {self.port}: {self.baudrate}: {self.bytesize}{self.parity}{self.stopbits}"

    def ammeter_report(self, wait=5):
        """ Returns the data table collected if the ammeter collection is complete, waits up to the specified time """
        cancel_time = time() + wait
        while time() < cancel_time:
            if self.ammeter_stop_time != {}:
                with self.ammeter_data_lock:
                    return {
                        'start': self.ammeter_start_time,
                        'stop': self.ammeter_stop_time,
                        'data': self.ammeter_data
                    }
        return None

    @property
    def ammeter_status(self):
        """ Get the current status of the ammeter """
        with self.ammeter_status_lock:
            self.ammeter_status_data == {}
        self.write('CMD:STATUS\n'.encode())
        endtime = time() + 3
        while time() < endtime:
            with self.ammeter_status_lock:
                if self.ammeter_status_data != {}:
                    return self.ammeter_status_data
        return {}

    @property
    def ammeter_initialized(self):
        """ Return True/False if ammeter is initialized """
        status = self.ammeter_status
        if status != {} and status['status'] == 'NOINIT':
            return False
        return True

    @property
    def ammeter_running(self):
        """ Return True/ False if sampling is in progress """
        status = self.ammeter_status
        if status != {} and status['status'] == 'RUNNING':
            return True
        return False

    @property
    def ammeter_ready(self):
        status = self.ammeter_status
        if status != {} and status['status'] == 'READY':
            return True
        return False

    @property
    def ammeter_config(self):
        """ Return the current configuration of the ammeter 
            Expecting: CONFIG:{interval}:{timeout}:{pin}:{name}:{baseline}[:{pin}:{name}:{baseline}...]
        """
        with self.ammeter_config_lock:
            self.ammeter_config_data = {}
        self.write('CMD:CONFIG\n'.encode())
        endtime = time() + 3
        while time() < endtime:
            with self.ammeter_config_lock:
                if self.ammeter_config_data != {}:
                    return self.ammeter_config_data
            sleep(.25)
        return {}

    @property
    def ammeter_interval(self):
        """ Return the current sampling interval """
        config = self.ammeter_config
        return config['interval']

    @ammeter_interval.setter
    def ammeter_interval(self, value:int):
        """ Update the sampling interval """
        self.write(f'CMD:INTERVAL:{int(value)}\n'.encode())
        sleep(.2)
        if self.ammeter_interval == value:
            return True
        return False

    def ammeter_init(self):
        """ Initialize the ammeter """
        self.write('CMD:INIT\n'.encode())

    def ammeter_start(self, timeout=None):
        """ Start the sampling """
        self.write((f"CMD:START{(':' + str(timeout)) if timeout is not None else ''}" + '\n').encode())
        stop_time = time() + 3
        while time() < stop_time:
            if self.ammeter_running:
                return True
            sleep(.25)
        return False

    def ammeter_stop(self):
        """ Stop the sampling if currently running """
        self.write('CMD:STOP\n'.encode())
        stop_time = time() + 3
        while time() < stop_time:
            if not self.ammeter_running:
                return True
            sleep(.25)
        return False

    @property
    def ammeter_current(self):
        """ Read one value and return """
        if not self.ammeter_running:
            self.write('CMD:ONE\n'.encode())
            self._ammeter_read()


    def _ammeter_read(self):
        """ Read any data waiting in the queue, if wait_for_response, wait until a non-data response is received """
        self._logger.info('%s: Starting backgroup ammeter read.', self._info_str)
        while True:
            with self.ammeter_data_lock:
                self.ammeter_partial_data += self.read(self.in_waiting).decode('utf-8')
            ammeter_temp_data = self.ammeter_partial_data.split('\n')
            while len(ammeter_temp_data) != 0:
                if self._ammeter_parse_read_line(ammeter_temp_data[0].split(':')):
                    with self.ammeter_data_lock:
                        ammeter_temp_data.pop(0)
                        self.ammeter_partial_data = '\n'.join(ammeter_temp_data)
                else:
                    # didn't find a complete line, if there are other lines then it must be corrupt
                    if len(ammeter_temp_data) > 1:
                        self._logger.warning('%s: Bad data: %s', self._info_str, ammeter_temp_data[0])
                        ammeter_temp_data.pop(0)
                        self.ammeter_partial_data = '\n'.join(ammeter_temp_data)
                    else:
                        # otherwise break out of the loop to wait for more data
                        with self.ammeter_data_lock:
                            self.ammeter_partial_data = '\n'.join(ammeter_temp_data)
                        break
            sleep(.1)


    def _ammeter_parse_read_line(self, response:list):
        """ Take a split list of data recieved from the ammeter and match it to a record """
        if response == ['']:
            # just remove any blank lines
            return True
        self._logger.debug('%s: Received data: %s', self._info_str, response)
        # if received a data point, log it to the array
        if response[0] == 'DATA':
            if len(response) == 6:
                with self.ammeter_data_lock:
                    self.ammeter_data.append({
                        'received': time(),
                        'name': response[1],
                        'ticks': int(response[2]),
                        'current_amps': float(response[3]),
                        'last_reads': literal_eval(response[4]),
                        'average': float(response[5])
                    })
                return True
            else:
                self._logger.error('%s: Invalid number of fields in DATA Transmission.  Received %i, expected 6', self._info_str, len(response))
        # if received a start response, udpate the start or end time
        if response[0] == 'START':
            if len(response) == 2:
                with self.ammeter_data_lock:
                    # clear the data table and set the start time
                    self.ammeter_data = []
                    starttime = time()
                    self.ammeter_start_time = {
                        'reported': int(response[1]),
                        'local': starttime
                    }
                    self.ammeter_stop_time = {}
                return True
            else:
                self._logger.error('%s: Invalid number of fields in START Transmission.  Received %i, expected 2', self._info_str, len(response))
        # if received a stop response, udpate the start or end time
        if response[0] == 'STOP':
            if len(response) == 2:
                with self.ammeter_data_lock:
                    # clear the data table and set the start time
                    stoptime = time()
                    self.ammeter_stop_time = {
                        'reported': int(response[1]),
                        'local': stoptime,
                        'runtime_reported': int(response[1]) - self.ammeter_start_time['reported'],
                        'runtime_local': stoptime - self.ammeter_start_time['local']
                    }
                return True
            else:
                self._logger.error('%s: Invalid number of fields in START Transmission.  Received %i, expected 2', self._info_str, len(response))
        # if received a config repsonse, update the current config
        if response[0] == 'CONFIG':
            if len(response) >= 7:
                with self.ammeter_config_lock:
                    self.ammeter_config_data = {
                        'interval': int(response[1]),
                        'timeout': int(response[2]),
                        'init_timeout': int(response[3]),
                        'pins': [
                            {
                                'pin': int(response[4]),
                                'name': response[5],
                                'baseline': int(response[6])
                            }
                        ]
                    }
                    if len(response) > 7 and (len(response) - 7) % 3 == 0:
                        for x in range(6, len(response), 3):
                            self.ammeter_config_data['pins'].append({})
                return True
            else:
                self._logger.error('%s: Invalid number of fields in CONFIG Transmission.  Received %i, expected >=6', self._info_str, len(response))
        # if received a status response, update the current status
        if response[0] == 'STATUS':
            if len(response) >= 2:
                with self.ammeter_status_lock:
                    self.ammeter_status_data = {
                        'status': response[1],
                        'timeout': response[2] if response[1] == 'INITIALIZING' or response[1] == 'RUNNING' else 0,
                        'noinit_pin': response[2] if response[1] == 'NOINIT' else None
                    }
                return True
            else:
                self._logger.error('%s: Invalid number of fields in STATUS Transmission.  Received %i, expected >=2', self._info_str, len(response))

        # didn't find a match, might not be a complete line
        return False
