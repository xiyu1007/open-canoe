/**
 * @file    device_config.h
 * @brief   Auto-selects the correct device config based on MCU define.
 *          Include this header in all driver source files.
 */

#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

#if defined(STM32F103xB)
  #include "f103/stm32f103_config.h"
#elif defined(STM32F407xx)
  #include "f407/stm32f407_config.h"
#else
  #error "Unsupported MCU target. Define STM32F103xB or STM32F407xx."
#endif

#endif /* DEVICE_CONFIG_H */
