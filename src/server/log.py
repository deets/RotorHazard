import sys
import logging.handlers

ROTORHAZARD_FORMAT = "RotorHazard: %(message)s"

SOCKET_IO = None

server_logger = logging.getLogger("server")
hardware_logger = logging.getLogger("hardware")
interface_logger = logging.getLogger("hardware")


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
        format=ROTORHAZARD_FORMAT,
    )
    # some 3rd party packages use logging. Good for them. Now be quiet.
    logging.getLogger("socketio.server").setLevel(logging.WARN)
    logging.getLogger("engineio.server").setLevel(logging.WARN)


def handler_for_config(destination):
    choices = {
        "STDERR": logging.StreamHandler(stream=sys.stderr),
        "STDOUT": logging.StreamHandler(stream=sys.stdout),
        "SYSLOG": logging.handlers.SysLogHandler("/dev/log")
    }
    if destination in choices:
        return choices[destination]
    # we assume if the entry is not amongst them
    # pre-defined choices, it's a filename
    return logging.FileHandler(destination)


def setup_logging_from_configuration(config, socket_io):
    global SOCKET_IO
    SOCKET_IO = socket_io

    logging_config = dict(
        LEVEL="INFO",
        DESTINATION="STDERR",
    )
    logging_config.update(config)
    root = logging.getLogger()
    # empty out the already configured handler
    # from basicConfig
    root.handlers[:] = []
    handler = handler_for_config(
        logging_config["DESTINATION"]
    )
    handler.setFormatter(logging.Formatter(ROTORHAZARD_FORMAT))
    root.setLevel(DEFAULT_LOGLEVEL)
    root.addHandler(handler)
