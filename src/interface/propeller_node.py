'''RotorHazard hardware interface layer.'''
import nanomsg
import struct
import gevent.select
from monotonic import monotonic

from log import hardware_log
from Node import Node
from RHInterface import (
    READ_FREQUENCY,
    READ_LAP_STATS,
    READ_REVISION_CODE,
    READ_NODE_RSSI_PEAK,
    READ_NODE_RSSI_NADIR,
    READ_ENTER_AT_LEVEL,
    READ_EXIT_AT_LEVEL,
    WRITE_FREQUENCY,
    WRITE_ENTER_AT_LEVEL,
    WRITE_EXIT_AT_LEVEL,
    )


RACEBAND = [5658, 5695, 5732, 5769, 5806, 5843, 5880, 5917]
NODE_API_LEVEL = 21

class PropellerNode(Node):

    def __init__(self, controller, index):
        Node.__init__(self)
        self._controller = controller
        self.index = index

    def node_log(self, interface, message):
        if interface:
            interface.log(message)
        else:
            hardware_log(message)

    def read_block(self, interface, command, size):
        '''
        Read serial data given command, and data size.
        '''
        self.io_request = monotonic()
        try:
            return self._controller.read_block(
                self.index,
                interface,
                command,
                size
            )
        finally:
            self.io_response = monotonic()


    def write_block(self, interface, command, data):
        '''
        Write serial data given command, and data.
        '''
        return self._controller.write_block(
            self.index,
            interface,
            command,
            data,
        )


class PropellerController:
    # We are big-endian here
    # because that's what RH used
    # in i2c-code. Might change that
    # B lap count
    # H ms since lap_id
    # B current rssi
    # B rssi peak
    # B pass rssi peak
    # H TBD
    # B flags
    # B pass rssi nadir
    # B node rssi nadir
    # BHH extremum
    LAP_STATS_RH = ">BHBBBHBBBBHH"
    LAP_STATS_RH_LEN = struct.calcsize(LAP_STATS_RH)
    # B enter_at level
    # B exit_at level
    LAP_STATS_DEETS = "BB"
    LAP_STATS_FORMAT = LAP_STATS_RH + LAP_STATS_DEETS
    LAP_STATS_LEN = struct.calcsize(LAP_STATS_FORMAT)

    def __init__(self, uri, count, nodes):
        self._socket = nanomsg.Socket(nanomsg.PAIR)
        self._socket.connect(uri)
        self._frequencies = list(RACEBAND)
        self._rssi_peaks = [100] * count
        self._rssi_nadirs = [20] * count
        self._enter_at_levels = [40] * count
        self._exit_at_levels = [80] * count
        self._raw_messages = [None] * count
        self._nodes = nodes

        for index in range(count):
            node = PropellerNode(self, index)
            nodes.append(node)
        t = gevent.Greenlet(run=self._read_thread)
        t.start()

    def _read_thread(self):
        while True:
            gevent.select.select([self._socket.recv_fd], [], [])
            msg = self._socket.recv()
            if msg.startswith(b"L"):
                self._process_lap_stats(msg[1:])

    def _process_lap_stats(self, msg):
        l = self.LAP_STATS_LEN
        assert len(msg) == len(self._nodes) * l
        for i in range(len(self._nodes)):
            part = msg[l * i:l * (i + 1)]
            lap_count, ms_since_lap, rssi, node_peak, rssi_pass, _, \
                flags, pass_nadir, node_nadir, \
                extremum_rssi, extremum_ts, extremum_duration, \
                enter_at, exit_at = values = struct.unpack(
                    self.LAP_STATS_FORMAT, part
                )
            self._rssi_peaks[i] = node_peak
            self._rssi_nadirs[i] = node_nadir
            self._enter_at_levels[i] = enter_at
            self._exit_at_levels[i] = exit_at
            self._raw_messages[i] = part[:self.LAP_STATS_RH_LEN]

    def read_block(self, index, interface, command, size):
        packed_data = {
            READ_FREQUENCY: self._read_frequency,
            READ_LAP_STATS: self._read_lap_stats,
            READ_REVISION_CODE: self._read_revision_code,
            READ_NODE_RSSI_PEAK: self._read_node_rssi_peak,
            READ_NODE_RSSI_NADIR: self._read_node_rssi_nadir,
            READ_ENTER_AT_LEVEL: self._read_enter_at_level,
            READ_EXIT_AT_LEVEL: self._read_exit_at_level,

        }[command](index, interface)
        return [ord(c) for c in packed_data] if packed_data is not None else None

    def _read_revision_code(self, index, interface):
        return struct.pack(">H", (0x25 << 8) + NODE_API_LEVEL)

    def _read_frequency(self, index, interface):
        return struct.pack(">H", self._frequencies[index])

    def _read_lap_stats(self, index, interface):
        return self._raw_messages[index]

    def _read_node_rssi_peak(self, index, interface):
        return struct.pack("B", self._rssi_peaks[index])

    def _read_node_rssi_nadir(self, index, interface):
        return struct.pack("B", self._rssi_nadirs[index])

    def _read_enter_at_level(self, index, interface):
        return struct.pack("B", self._enter_at_levels[index])

    def _read_exit_at_level(self, index, interface):
        return struct.pack("B", self._exit_at_levels[index])

    def write_block(self, index, interface,  command, data):
        data = "".join(chr(v) for v in data)
        {
            WRITE_FREQUENCY: self._write_frequency,
            WRITE_ENTER_AT_LEVEL: self._write_enter_at,
            WRITE_EXIT_AT_LEVEL: self._write_exit_at,

        }[command](index, data)
        # we always write the full configuration on
        # any incoming block
        self._update_node_state()

    def _update_node_state(self):
        res = []
        for frequency, enter_at, exit_at in zip(
                self._frequencies,
                self._enter_at_levels,
                self._exit_at_levels):
            res.append(struct.pack("<HBB", frequency, enter_at, exit_at))
        message = "C" + b"".join(res)
        self._socket.send(message)

    def _write_frequency(self, index, data):
        self._frequencies[index] = struct.unpack(">H", data)[0]

    def _write_enter_at(self, index, data):
        self._enter_at_levels[index] = struct.unpack(">B", data)[0]

    def _write_exit_at(self, index, data):
        self._exit_at_levels[index] = struct.unpack(">B", data)[0]


def discover(idxOffset, *args, **kwargs):
    nodes = []
    config = kwargs['config']
    config = getattr(config, 'PROPELLER', {})
    if config:
        uri = config["URI"]
        count = config["COUNT"]
        PropellerController(uri, count, nodes)
    return nodes
