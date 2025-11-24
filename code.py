import time
import board
import busio
from adafruit_emc2101 import EMC2101
import digitalio
import neopixel
import math

MIN_TEMP = 10  # Temperature Boundaries. Closer to this is green. LEDs
MAX_TEMP = 50  # Temperature Boundaries. Closer to this is red. LEDs
LEDBRIGHTNESS = 0.1  # Yes, you can change the brightness here
BAUD_RATE = 115200  # The UART connection speed
TIMEOUT = 1  # Number of time before timeout
TEMP_OFFSET = 0  # degrees C Correction for internal_temperature to match external_temperature.

LED = digitalio.DigitalInOut(board.LED)
LED.direction = digitalio.Direction.OUTPUT

PIXELS = neopixel.NeoPixel(board.GP15, 2, brightness=LEDBRIGHTNESS, auto_write=False, pixel_order="GRB")

BUTTON = digitalio.DigitalInOut(board.GP12)  # Button on the back of the fan unit

FAN_POWER = digitalio.DigitalInOut(board.GP16)  # The fan power control is on GPIO16 you can turn it off/on.
FAN_POWER.direction = digitalio.Direction.OUTPUT
FAN_POWER.value = True  # Turn on Fan

UART0 = busio.UART(board.GP0, board.GP1, baudrate=BAUD_RATE, timeout=TIMEOUT)
UART1 = busio.UART(board.GP8, board.GP9, baudrate=BAUD_RATE, timeout=TIMEOUT)
I2C = busio.I2C(board.GP5, board.GP4)
emc = EMC2101(I2C)

# Initialize previous values to persist when no new data is received
prev_dataA = 'Auto'
prev_dataB = 'Auto'

# Apply offset in function
def getInternalWithOffset():
    return emc.internal_temperature + TEMP_OFFSET

# Set Fan Speed 0 < 100
def setFanSpeed(speed: int):
    if speed < 0:
        speed = 0
    elif speed > 100:
        speed = 100
    emc.manual_fan_speed = speed
    time.sleep(1)

# Compare to see if the external or internal temperature are in the range
def checkTempInRange(low: int, high: int):
    return low <= emc.external_temperature < high or low <= getInternalWithOffset() < high

# Color of digital LEDs depending on the temperature readings
def smoothLED(temp: int | float, position: int):
    # Smoothly changes the color within the set values
    if MIN_TEMP <= temp <= MAX_TEMP:
        temp = temp - MIN_TEMP
        max_min_delta = MAX_TEMP - MIN_TEMP
        c = int(round((temp / max_min_delta) * 100))
        a = int(round((510 / 100) * c))
        if a > 255:
            red = 255
            green = 510 - a
        else:
            red = a
            green = 255
        PIXELS[position] = (green, red, 0)
    elif temp < MIN_TEMP:
        PIXELS[position] = (255, 0, 0)
    else:
        PIXELS[position] = (0, 255, 0)

while True:
    # Change LED color based on Temp
    smoothLED(emc.external_temperature, 0)
    smoothLED(getInternalWithOffset(), 1)
    PIXELS.show()
    time.sleep(0.1)

    dataA_raw = UART0.read(8)
    dataB_raw = UART1.read(8)

    # Only update dataA if valid data is received
    if dataA_raw is not None:
        try:
            decoded = dataA_raw.decode().strip()
            if decoded.lower() == 'auto':
                prev_dataA = 'Auto'
            else:
                prev_dataA = int(decoded)
        except:
            pass  # Keep previous value if parsing fails

    # Only update dataB if valid data is received
    if dataB_raw is not None:
        try:
            decoded = dataB_raw.decode().strip()
            if decoded.lower() == 'auto':
                prev_dataB = 'Auto'
            else:
                prev_dataB = int(decoded)
        except:
            pass  # Keep previous value if parsing fails

    dataA = prev_dataA
    dataB = prev_dataB

    if BUTTON.value:
        LED.value = False

    else:
        LED.value = True

    BladeA_uart_info = bytes(str("Internal temperature(Port A): " + str(getInternalWithOffset()) + " C" + "\r\n"), 'UTF-8')
    BladeB_uart_info = bytes(str("External temperature(Port B): " + str(emc.external_temperature) + " C" + "\r\n"), 'UTF-8')

    fan_speed = bytes(str("Fan speed: " + str(emc.fan_speed) + "RPM (" + str(math.floor(emc.manual_fan_speed)) + "%)" + "\r\n" + "\r\n"), 'UTF-8')
    blade_request = bytes(str("Blade A requested: " + str(dataA) + "% | Blade B requested: " + str(dataB) + "%" + "\r\n"), 'UTF-8')
    UART0.write(BladeA_uart_info + BladeB_uart_info + blade_request + fan_speed)
    UART1.write(BladeA_uart_info + BladeB_uart_info + blade_request + fan_speed)

    # Both blades have requested manual control.
    if dataA is not 'Auto' and dataB is not 'Auto':
        setFanSpeed(int(max(dataA, dataB)))
    # Only blade A has requested manual control.
    elif dataA is not 'Auto':
        LED.value = True
        print("Set the speed as Blade A asks:", dataA, " %")
        # Don't let the speed go lower than 10% if one blade is still "Auto"
        setFanSpeed(int(max(10, dataA)))
    # Only blade B has requested manual control.
    elif dataB is not 'Auto':
        LED.value = True
        print("Set the speed as Blade B asks:", dataB, " %")
        # Don't let the speed go lower than 10% if one blade is still "Auto"
        setFanSpeed(int(max(10, dataB)))
    # Automatic control is enabled.
    else:
        if 50 <= emc.external_temperature or 50 <= getInternalWithOffset():
            setFanSpeed(100)
        elif checkTempInRange(45, 50):
            setFanSpeed(70)
        elif checkTempInRange(40, 45):
            setFanSpeed(60)
        elif checkTempInRange(35, 40):
            setFanSpeed(40)
        elif checkTempInRange(30, 35):
            setFanSpeed(30)
        else:
            setFanSpeed(10)