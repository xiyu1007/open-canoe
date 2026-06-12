/**
 * @file    comm_driver.c
 * @brief   Communication driver using STM32 HAL UART API (interrupt mode).
 *          USART + optional USB CDC. Supports runtime interface switching.
 */

#include "comm_api.h"
#include "device_api.h"
#include "device_config.h"
#include "protocol.h"
#include <string.h>

#if defined(STM32F103xB)
#include "stm32f1xx_hal.h"
#elif defined(STM32F407xx)
#include "stm32f4xx_hal.h"
#endif

#if HAS_USB_CDC
#if defined(STM32F407xx)
#include "stm32f4xx_hal_pcd.h"
#include "usbd_core.h"
#include "usbd_desc.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#endif
#endif

/*============================================================================
 * Internal State
 *============================================================================*/

static UART_HandleTypeDef g_uart_handle;
static uint8_t           g_comm_initialized = 0;
static comm_config_t     g_comm_config;

/* RX ring buffer (filled from ISR, drained by main loop) */
static uint8_t           g_rx_byte;
static uint8_t           g_rx_buf[COMM_RX_BUF_SIZE];
static volatile uint16_t g_rx_head = 0;
static volatile uint16_t g_rx_tail = 0;

/*============================================================================
 * USART MSP Initialization
 *============================================================================*/

static void comm_usart_msp_init(uint32_t baudrate)
{
    COMM_USART_GPIO_CLK_ENABLE();
    COMM_USART_CLK_ENABLE();

    /* TX pin */
    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_AF_PP;
    gpio.Pull  = GPIO_PULLUP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pin   = COMM_USART_TX_PIN;
#if defined(STM32F407xx)
    gpio.Alternate = GPIO_AF7_USART1;
#endif
    HAL_GPIO_Init(COMM_USART_TX_PORT, &gpio);

    /* RX pin */
    gpio.Mode  = GPIO_MODE_INPUT;
    gpio.Pull  = GPIO_PULLUP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pin   = COMM_USART_RX_PIN;
    HAL_GPIO_Init(COMM_USART_RX_PORT, &gpio);

    /* USART config */
    memset(&g_uart_handle, 0, sizeof(g_uart_handle));
    g_uart_handle.Instance          = COMM_USART;
    g_uart_handle.Init.BaudRate     = baudrate;
    g_uart_handle.Init.WordLength   = UART_WORDLENGTH_8B;
    g_uart_handle.Init.StopBits     = UART_STOPBITS_1;
    g_uart_handle.Init.Parity       = UART_PARITY_NONE;
    g_uart_handle.Init.Mode         = UART_MODE_TX_RX;
    g_uart_handle.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    g_uart_handle.Init.OverSampling = UART_OVERSAMPLING_16;

    HAL_UART_Init(&g_uart_handle);

    /* Enable USART interrupt in NVIC */
    HAL_NVIC_SetPriority(COMM_USART_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(COMM_USART_IRQn);

    /* Start interrupt-based receive (1 byte at a time) */
    HAL_UART_Receive_IT(&g_uart_handle, &g_rx_byte, 1);
}

/*============================================================================
 * USB CDC MSP Initialization (F4 only)
 *============================================================================*/

#if HAS_USB_CDC
static void comm_usb_cdc_msp_init(void)
{
    USB_CDC_CLK_ENABLE();
    USB_CDC_GPIO_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_AF_PP;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    gpio.Pin       = USB_CDC_DP_PIN;
    gpio.Alternate = GPIO_AF10_OTG_FS;
    HAL_GPIO_Init(USB_CDC_DP_PORT, &gpio);
    gpio.Pin       = USB_CDC_DM_PIN;
    HAL_GPIO_Init(USB_CDC_DM_PORT, &gpio);
    gpio.Pin       = USB_CDC_ID_PIN;
    HAL_GPIO_Init(USB_CDC_ID_PORT, &gpio);
    gpio.Pull      = GPIO_PULLUP;
    gpio.Pin       = USB_CDC_VBUS_PIN;
    HAL_GPIO_Init(USB_CDC_VBUS_PORT, &gpio);

    HAL_NVIC_SetPriority(USB_CDC_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(USB_CDC_IRQn);
}
#endif

/*============================================================================
 * USART ISR Callback (called from HAL_UART_IRQHandler)
 *============================================================================*/

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart == &g_uart_handle) {
        uint16_t next = (g_rx_head + 1) % COMM_RX_BUF_SIZE;
        if (next != g_rx_tail) {
            g_rx_buf[g_rx_head] = g_rx_byte;
            g_rx_head = next;
        }
        /* Re-arm for next byte */
        HAL_UART_Receive_IT(&g_uart_handle, &g_rx_byte, 1);
    }
}

/**
 * @brief USART IRQ handler — delegates to HAL.
 */
void COMM_USART_IRQHandler(void)
{
    HAL_UART_IRQHandler(&g_uart_handle);
}

/*============================================================================
 * Public API
 *============================================================================*/

comm_status_t comm_init(const comm_config_t *config)
{
    if (!config) return COMM_ERR_PARAM;
    memcpy(&g_comm_config, config, sizeof(comm_config_t));

    if (config->type == COMM_IF_USB_CDC) {
#if HAS_USB_CDC
        comm_usb_cdc_msp_init();
#else
        return COMM_ERR_HW;
#endif
    }

    comm_usart_msp_init(config->baudrate);
    g_comm_initialized = 1;
    return COMM_OK;
}

comm_status_t comm_switch_interface(comm_interface_t new_type, uint32_t baudrate)
{
    if (!g_comm_initialized) return COMM_ERR_NOT_INIT;

    HAL_UART_DeInit(&g_uart_handle);

    if (new_type == COMM_IF_USB_CDC) {
#if HAS_USB_CDC
        comm_usb_cdc_msp_init();
#else
        return COMM_ERR_SWITCH_FAILED;
#endif
    } else {
        comm_usart_msp_init(baudrate);
    }

    g_comm_config.type = new_type;
    g_comm_config.baudrate = baudrate;
    return COMM_OK;
}

comm_interface_t comm_get_current_interface(void)
{
    return g_comm_config.type;
}

comm_status_t comm_send(const uint8_t *data, uint16_t length,
                        uint32_t timeout_ms)
{
    if (!g_comm_initialized) return COMM_ERR_NOT_INIT;
    if (!data || length == 0) return COMM_OK;

    if (g_comm_config.type == COMM_IF_USB_CDC) {
#if HAS_USB_CDC
        USBD_CDC_SetTxBuffer(NULL, (uint8_t *)data, length);
        USBD_CDC_TransmitPacket(NULL);
        return COMM_OK;
#else
        return COMM_ERR_HW;
#endif
    }

    HAL_StatusTypeDef ret = HAL_UART_Transmit(&g_uart_handle,
                                               (uint8_t *)data, length,
                                               timeout_ms);
    return (ret == HAL_OK) ? COMM_OK : COMM_ERR_TX_FAILED;
}

comm_status_t comm_receive(uint8_t *buffer, uint16_t max_len,
                           uint16_t *recv_len, uint32_t timeout_ms)
{
    if (!g_comm_initialized) return COMM_ERR_NOT_INIT;
    if (!buffer || !recv_len) return COMM_ERR_PARAM;

    *recv_len = 0;
    (void)timeout_ms;

    /* Pull bytes from ISR-filled ring buffer (non-blocking) */
    while (*recv_len < max_len && g_rx_head != g_rx_tail) {
        buffer[(*recv_len)++] = g_rx_buf[g_rx_tail];
        g_rx_tail = (g_rx_tail + 1) % COMM_RX_BUF_SIZE;
    }

    return COMM_OK;
}

comm_status_t comm_register_rx_callback(comm_rx_callback_t callback)
{
    (void)callback;
    return COMM_OK;
}

comm_status_t comm_send_heartbeat(void)
{
    extern int protocol_send_heartbeat(void);
    protocol_send_heartbeat();
    return COMM_OK;
}

comm_status_t comm_flush_tx(void)
{
    return COMM_OK;
}

uint8_t comm_is_ready(void)
{
    return g_comm_initialized;
}

uint8_t comm_usb_cdc_available(void)
{
#if HAS_USB_CDC
    return 1;
#else
    return 0;
#endif
}
