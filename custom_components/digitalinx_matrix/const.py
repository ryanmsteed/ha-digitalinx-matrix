"""Constants for the DigitaLinx HDMI Matrix integration."""

DOMAIN = "digitalinx_matrix"

CONF_NUM_INPUTS = "num_inputs"
CONF_NUM_OUTPUTS = "num_outputs"
CONF_INPUT_NAMES = "input_names"

DEFAULT_PORT = 23
DEFAULT_NAME = "DigitaLinx Matrix"
DEFAULT_NUM_INPUTS = 4
DEFAULT_NUM_OUTPUTS = 2
DEFAULT_TIMEOUT = 5

# DL-S42-H2 TCP/IP protocol commands (ASCII, CR+LF terminated)
# All commands and responses use \r\n (0x0D 0x0A)
# Note: GET SW is not supported on firmware 3.6 — state is tracked
# from SET SW confirmations instead.
CMD_SET_SWITCH = "SET SW in{input} out{output}"    # Route input to output
CMD_GET_VERSION = "GET VER"                          # Query firmware version
CMD_REBOOT = "REBOOT"                               # Reboot device
CMD_FACTORY_RESET = "RESET"                          # Factory reset

COMMAND_TERMINATOR = "\r\n"
