import unittest
from unittest.mock import patch

from deepcool_linux.hardware import HidWriter


class HidTransportTests(unittest.TestCase):
    def setUp(self):
        self.device = HidWriter()
        self.device.fd = 123

    def test_get_feature_uses_descriptor_size_and_report_id(self):
        def ioctl(fd, op, data, mutate):
            self.assertEqual(fd, 123)
            self.assertEqual(op, 0xC0404807)
            self.assertEqual(data[0], 3)
            data[1] = 42
            return len(data)
        with patch('deepcool_linux.hardware.fcntl.ioctl', side_effect=ioctl):
            self.assertEqual(self.device.get_feature(3)[:2], b'\x03\x2a')

    def test_short_feature_response_is_not_padded(self):
        with patch('deepcool_linux.hardware.fcntl.ioctl', return_value=2):
            self.assertEqual(len(self.device.get_feature(3)), 2)

    def test_reject_unknown_ids_before_ioctl(self):
        with patch('deepcool_linux.hardware.fcntl.ioctl') as ioctl:
            with self.assertRaises(ValueError):
                self.device.get_feature(6)
            with self.assertRaises(ValueError):
                self.device.send_feature(b'\x06\0')
            with self.assertRaises(ValueError):
                self.device.send_feature(b'\x03\0')
            ioctl.assert_not_called()

    def test_short_feature_write_closes_connection(self):
        with patch('deepcool_linux.hardware.fcntl.ioctl', return_value=1), \
             patch('deepcool_linux.hardware.os.close') as close:
            with self.assertRaises(OSError):
                self.device.send_feature(b'\x05\x01')
            close.assert_called_once_with(123)
            self.assertIsNone(self.device.fd)

    def test_nonblocking_input_budget(self):
        with patch('deepcool_linux.hardware.os.read', side_effect=[b'\x10\x01', BlockingIOError()]):
            self.assertEqual(self.device.read_inputs(), [b'\x10\x01'])


if __name__ == '__main__':
    unittest.main()
