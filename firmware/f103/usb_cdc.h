/**
 * @file usb_cdc.h
 * @brief USB CDC (virtual COM port) abstraction for STM32F103.
 *
 * F103C8T6 USB is Full Speed (12 Mbps). CDC class presents as
 * /dev/ttyACMx (Linux) or COMx (Windows).
 */

#ifndef USB_CDC_H
#define USB_CDC_H

#include <stdint.h>

void usb_cdc_init(void);
void usb_cdc_write_byte(uint8_t byte);
int  usb_cdc_read_byte(uint8_t *byte);
int  usb_cdc_available(void);

#endif /* USB_CDC_H */
