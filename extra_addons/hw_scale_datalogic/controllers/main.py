# -*- coding: utf-8 -*-
import logging
import simplejson
import os
import time
from os import listdir
from os.path import join
from threading import Thread, Lock
from select import select
from Queue import Queue, Empty
from serial import Serial
import curses.ascii

import openerp
import openerp.addons.hw_proxy.controllers.main as hw_proxy
from openerp import http
from openerp.http import request
from openerp.tools.config import config
from openerp.tools.translate import _

_logger = logging.getLogger(__name__)

try:
    import serial
except ImportError:
    _logger.error('Odoo module hw_scale depends on the pyserial python module')
    serial = None


class ScaleDatalogic(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.lock = Lock()
        self.scalelock = Lock()
        self.status = {
                       'status': 'connecting',
                       'messages': [],
                       }
        self.input_dir = '/dev/serial/by-path/'
        self.weight = 0
        self.weight_info = 'ok'
        self.device = None
        self.probed_device_paths = []
        self.path_to_scale = ''
        self.device_name = config.get(
            'telium_terminal_device_name', '/dev/tty0')
        self.device_rate = int(config.get(
            'telium_terminal_device_rate', 9600))
        self.serial = False

    def lockedstart(self):
        with self.lock:
            if not self.isAlive():
                self.daemon = True
                self.start()

    def push_task(self, task, data=None):
        self.lockedstart()
        self.queue.put((time.time(), task, data))

    def serial_write(self, text):
        assert isinstance(text, str), 'text must be a string'
        self.serial.write(text)

    def initialize_msg(self):
        max_attempt = 3
        attempt_nr = 0
        while attempt_nr < max_attempt:
            attempt_nr += 1
            self.send_one_byte_signal('ENQ')
            if self.get_one_byte_answer('ACK'):
                return True
            else:
                _logger.warning("Scale : SAME PLAYER TRY AGAIN")
                self.send_one_byte_signal('EOT')
                # Wait 1 sec between each attempt
                time.sleep(1)
        return False

    def send_one_byte_signal(self, signal):
        ascii_names = curses.ascii.controlnames
        assert signal in ascii_names, 'Wrong signal'
        char = ascii_names.index(signal)
        self.serial_write(chr(char))
        _logger.debug('Signal %s sent to Scale' % signal)

    def get_one_byte_answer(self, expected_signal):
        ascii_names = curses.ascii.controlnames
        one_byte_read = self.serial.read(1)
        expected_char = ascii_names.index(expected_signal)
        if one_byte_read == chr(expected_char):
            _logger.debug("%s received from Scale" % expected_signal)
            return True
        else:
            return False

    def generate_lrc(self, real_msg_with_etx):
        lrc = 0
        for char in real_msg_with_etx:
            lrc ^= ord(char)
        return lrc

    def send_message(self, data=[]):
        '''We use protocol E+'''
        ascii_names = curses.ascii.controlnames
        real_msg = chr(ascii_names.index('ESC')).join(data)
        _logger.debug('Real message to send = %s' % real_msg)
        real_msg_with_etx = real_msg + chr(ascii_names.index('ETX'))
        lrc = self.generate_lrc(real_msg_with_etx)
        message = chr(ascii_names.index('STX')) + real_msg_with_etx + chr(lrc)
        self.serial_write(message)
        _logger.info('Message sent to terminal')

    def get_answer_from_terminal(self, data):
        ascii_names = curses.ascii.controlnames
        full_msg_size = 1+2+1+2+1+5+1+6+1+6+1+4+1
        msg = self.serial.read(size=full_msg_size)
        _logger.debug('%d bytes read from scale' % full_msg_size)
        assert len(msg) == full_msg_size, 'Answer has a wrong size'
        if msg[0] != chr(ascii_names.index('STX')):
            _logger.error(
                'The first byte of the answer from terminal should be STX')
        if msg[-2] != chr(ascii_names.index('ETX')):
            _logger.error(
                'The byte before final of the answer from terminal '
                'should be ETX')
        lrc = msg[-1]
        computed_lrc = chr(self.generate_lrc(msg[1:-1]))
        if computed_lrc != lrc:
            _logger.error(
                'The LRC of the answer from terminal is wrong')
        real_msg = msg[1:-2]
        _logger.debug('Real answer received = %s' % real_msg)
        return self.parse_terminal_answer(real_msg, data)

#     def set_status(self, status, message = None):
#         if status == self.status['status']:
#             if message != None and message != self.status['messages'][-1]:
#                 self.status['messages'].append(message)
# 
#                 if status == 'error' and message:
#                     _logger.error('Scale Error: '+message)
#                 elif status == 'disconnected' and message:
#                     _logger.warning('Disconnected Scale: '+message)
#         else:
#             self.status['status'] = status
#             if message:
#                 self.status['messages'] = [message]
#             else:
#                 self.status['messages'] = []
# 
#             if status == 'error' and message:
#                 _logger.error('Scale Error: '+message)
#             elif status == 'disconnected' and message:
#                 _logger.info('Disconnected Scale: %s', message)

    def _get_raw_response(self, connection):
        response = ""
        while True:
            byte = connection.read(1)
            if byte:
                response += byte
            else:
                return response

#     def get_device(self):
#         try:
#             if not os.path.exists(self.input_dir):
#                 self.set_status('disconnected','Scale Not Found')
#                 return None
#             devices = [ device for device in listdir(self.input_dir)]
# 
#             if len(devices) > 0:
#                 for device in devices:
#                     path = self.input_dir + device
# 
#                     # don't keep probing devices that are not a scale,
#                     # only keep probing if in the past the device was
#                     # confirmed to be a scale
#                     if path not in self.probed_device_paths or path == self.path_to_scale:
#                         _logger.debug('Probing: ' + path)
#                         connection = serial.Serial(path,
#                                                    baudrate = 9600,
#                                                    bytesize = serial.SEVENBITS,
#                                                    stopbits = serial.STOPBITS_ONE,
#                                                    parity   = serial.PARITY_EVEN,
#                                                    timeout  = 1,
#                                                    writeTimeout = 1)
# 
#                         connection.write("W")
#                         self.probed_device_paths.append(path)
# 
#                         if self._get_raw_response(connection):
#                             _logger.debug(path + ' is scale')
#                             self.path_to_scale = path
#                             self.set_status('connected', 'Connected to '+device)
#                             connection.timeout = 0.02
#                             connection.writeTimeout = 0.02
#                             return connection
#                     else:
#                         _logger.debug('Already probed: ' + path)
# 
#             self.set_status('disconnected', 'Scale Not Found')
#             return None
#         except Exception as e:
#             self.set_status('error', str(e))
#             return None
#

    def get_weight_info(self):
#         self.lockedstart()
        return self.weight_info

    def get_status(self):
#         self.lockedstart()
        return self.status
# 
#     def read_weight(self):
#         with self.scalelock:
#             if self.device:
#                 try:
#                     self.device.write('W')
#                     time.sleep(0.2)
#                     answer = []
# 
#                     while True:
#                         char = self.device.read(1)
#                         if not char:
#                             break
#                         else:
#                             answer.append(char)
# 
#                     if '?' in answer:
#                         stat = ord(answer[answer.index('?')+1])
#                         if stat == 0: 
#                             self.weight_info = 'ok'
#                         else:
#                             self.weight_info = []
#                             if stat & 1:
#                                 self.weight_info.append('moving')
#                             if stat & 1 << 1:
#                                 self.weight_info.append('over_capacity')
#                             if stat & 1 << 2:
#                                 self.weight_info.append('negative')
#                                 self.weight = 0.0
#                             if stat & 1 << 3:
#                                 self.weight_info.append('outside_zero_capture_range')
#                             if stat & 1 << 4:
#                                 self.weight_info.append('center_of_zero')
#                             if stat & 1 << 5:
#                                 self.weight_info.append('net_weight')
#                     else:
#                         answer = answer[1:-1]
#                         if 'N' in answer:
#                             answer = answer[0:-1]
#                         try:
#                             self.weight = float(''.join(answer))
#                         except ValueError as v:
#                             self.set_status('error',
#                                             'No data Received, please power-cycle the scale');
#                             self.device = None
# 
#                 except Exception as e:
#                     self.set_status('error', str(e))
#                     self.device = None
# 
#     def set_zero(self):
#         with self.scalelock:
#             if self.device:
#                 try:
#                     self.device.write('Z')
#                 except Exception as e:
#                     self.set_status('error', str(e))
#                     self.device = None
# 
#     def set_tare(self):
#         with self.scalelock:
#             if self.device:
#                 try:
#                     self.device.write('T')
#                 except Exception as e:
#                     self.set_status('error', str(e))
#                     self.device = None
# 
#     def clear_tare(self):
#         with self.scalelock:
#             if self.device:
#                 try:
#                     self.device.write('C')
#                 except Exception as e:
#                     self.set_status('error', str(e))
#                     self.device = None
# 
#     def run(self):
#         self.device = None
# 
#         while True:
#             if self.device:
#                 self.read_weight()
#                 time.sleep(0.15)
#             else:
#                 with self.scalelock:
#                     self.device = self.get_device()
#                 if not self.device:
#                     time.sleep(5)

    def get_weight(self):
        self.weight = 1
        try:
            _logger.info(
                'Opening serial port %s for scale with baudrate %d'
                % (self.device_name, self.device_rate))
            # TODO: make it workable
#             self.serial = Serial(
#                 self.device_name, self.device_rate,
#                 timeout=3)
#             _logger.debug('serial.is_open = %s' % self.serial.isOpen())
            if self.initialize_msg():
                data = ['71']
                self.send_message(data)
                if self.get_one_byte_answer('NAK'):
                    # TODO: check which error and explain it to the user
                    'error'
                else:
                    # TODO: Implement return
                    'ok'
#                     self.send_one_byte_signal('EOT')
# 
#                     _logger.info("Now expecting answer from Terminal")
#                     wait_terminal_answer = payment_info_dict.\
#                         get('wait_terminal_answer', False)
#                     if wait_terminal_answer:
#                         i = 0
#                         while i < 60:
#                             if self.get_one_byte_answer('ENQ'):
#                                 self.send_one_byte_signal('ACK')
#                                 answer = self.get_answer_from_terminal(data)
#                                 self.send_one_byte_signal('ACK')
#                                 if self.get_one_byte_answer('EOT'):
#                                     logger.info("Answer received from Terminal")
#                                 break
#                             time.sleep(1)
#                             i += 1
#                     else:
#                         if self.get_one_byte_answer('ENQ'):
#                             self.send_one_byte_signal('ACK')
#                             answer = self.get_answer_from_terminal(data)
#                             self.send_one_byte_signal('ACK')
#                             if self.get_one_byte_answer('EOT'):
#                                 _logger.info("Answer received from Terminal")
#                     _logger.warning(answer)
        except Exception, e:
            _logger.error('Exception in serial connection: %s' % str(e))
        finally:
            if self.serial:
                _logger.debug('Closing serial port for Datalogic scale.')
                self.serial.close()
        return self.weight

scale_thread = None
if serial:
    scale_thread = ScaleDatalogic()
    hw_proxy.drivers['scale_datalogic'] = scale_thread


class ScaleDatalogicDriver(hw_proxy.Proxy):

    @http.route(
        '/hw_proxy/scale_datalogic_read',
        type='json', auth='none', cors='*')
    def scale_datalogic_read(self):
        if scale_thread:
            return {
                    'weight': scale_thread.get_weight(),
                    'unit': 'kg',
                    'info': scale_thread.get_weight_info(),
                    }
        return None

#     @http.route('/hw_proxy/scale_zero/', type='json', auth='none', cors='*')
#     def scale_zero(self):
#         if scale_thread:
#             scale_thread.set_zero()
#         return True
# 
#     @http.route('/hw_proxy/scale_tare/', type='json', auth='none', cors='*')
#     def scale_tare(self):
#         if scale_thread:
#             scale_thread.set_tare()
#         return True
# 
#     @http.route('/hw_proxy/scale_clear_tare/', type='json', auth='none', cors='*')
#     def scale_clear_tare(self):
#         if scale_thread:
#             scale_thread.clear_tare()
#         return True
