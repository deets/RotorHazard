import sys
import logging

server_logger = logging.getLogger("server")
hardware_logger = logging.getLogger("hardware")
interface_logger = logging.getLogger("hardware")

SOCKET_IO = None


def server_log(message):
    '''Messages emitted from the server script.'''
    server_logger.info(message)
    if SOCKET_IO is not None:
        SOCKET_IO.emit('hardware_log', message)


def hardware_log(message):
    '''Message emitted from the interface class.'''
    hardware_logger.info(message)
    if SOCKET_IO is not None:
        SOCKET_IO.emit('hardware_log', message)


def setup_initial_logging():
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
    )
    # some 3rd party packages use logging. Good for them. Now be quiet.
    logging.getLogger("socketio.server").setLevel(logging.WARN)
    logging.getLogger("engineio.server").setLevel(logging.WARN)


def setup_logging_from_configuration(config, socket_io):
    global SOCKET_IO
    SOCKET_IO = socket_io
