"""
Support for Broadlink MP1 Power Strip devices.

Author: C.Soult
Date: 2018/7/9

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/switch.broadlink/
"""
from datetime import timedelta
from base64 import b64encode, b64decode
import asyncio
import binascii
import logging
import socket

import voluptuous as vol

from broadlink import mp1 as BroadlinkMP1Device
import homeassistant.loader as loader
from homeassistant.util.dt import utcnow
from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA)
from homeassistant.const import (
    CONF_FRIENDLY_NAME, CONF_ALIAS,
    CONF_TIMEOUT, CONF_HOST, CONF_MAC, CONF_TYPE)
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['broadlink']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'broadlink_mp1'
DEFAULT_NAME = 'Broadlink MP1 Power Strip'
DEFAULT_TIMEOUT = 10
DEFAULT_RETRY = 3
SERVICE_SEND = 'send_packet'

SWITCH_TYPES = ['mp1']

ALIAS_SCHEMA = vol.Schema({
    vol.Optional("s1"): cv.string,
    vol.Optional("s2"): cv.string,
    vol.Optional("s3"): cv.string,
    vol.Optional("s4"): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_ALIAS):
        vol.Schema({
            vol.Optional("s1"): cv.string,
            vol.Optional("s2"): cv.string,
            vol.Optional("s3"): cv.string,
            vol.Optional("s4"): cv.string,
        }),
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TYPE, default=SWITCH_TYPES[0]): vol.In(SWITCH_TYPES),
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up Broadlink switches."""
    import broadlink

    ip_addr = config.get(CONF_HOST)
    friendly_name = config.get(CONF_FRIENDLY_NAME)
    alias_names = config.get(CONF_ALIAS)
    mac_addr = binascii.unhexlify(
        config.get(CONF_MAC).encode().replace(b':', b''))
    switch_type = config.get(CONF_TYPE)

    persistent_notification = loader.get_component(hass,'persistent_notification')

    @asyncio.coroutine
    def _send_packet(call):
        packets = call.data.get('packet', [])
        for packet in packets:
            for retry in range(DEFAULT_RETRY):
                try:
                    payload = b64decode(packet)
                    yield from hass.async_add_job(
                        broadlink_device.send_data, payload)
                    break
                except (socket.timeout, ValueError):
                    try:
                        yield from hass.async_add_job(
                            broadlink_device.auth)
                    except socket.timeout:
                        if retry == DEFAULT_RETRY-1:
                            _LOGGER.error("Failed to send packet to device")

    broadlink_device = BroadlinkMP1Powerstrip((ip_addr, 80), mac_addr)
    switches = []
    for switch_id in range(1, 5):
        switch_alias = ('s' + str(switch_id))
        if (switch_alias in alias_names):
            switch_alias = alias_names['s' + str(switch_id)]
        switches.append(
            BroadlinkMP1Switch(
                switch_id,
                switch_alias,
                broadlink_device
            )
        )
    add_devices(switches)
    broadlink_device.timeout = config.get(CONF_TIMEOUT)
    broadlink_device.connect()


class BroadlinkMP1Powerstrip(BroadlinkMP1Device):
    def __init__(self, host, mac):
        super(BroadlinkMP1Powerstrip, self).__init__(host, mac, None)
        self._last_check_time = utcnow()
        self._connected = False
        self._state = {}

    def _auth(self, retry=2):
        try:
            auth = self.auth()
        except socket.timeout:
            auth = False
        if not auth and retry > 0:
            return self._auth(retry-1)
        return auth

    def connect(self):
        self._connected = self._auth()
        if not self._connected:
            _LOGGER.error("Failed to connect to device")

    def _update(self, retry=2):
        try:
            state = self.check_power()
        except (socket.timeout, ValueError) as error:
            if retry < 1:
                _LOGGER.error(error)
                return
            if not self._auth():
                return
            return self._update(retry-1)
        if state is None and retry > 0:
            return self._update(retry-1)
        self._state = state

    def update(self, force = False, retry=2):
        if not self._connected:
            _LOGGER.debug("Broadlink powerstrip ot connected yet")
            data = {}
            data['s1'] = False
            data['s2'] = False
            data['s3'] = False
            data['s4'] = False
            self._state = data
            return
        _check_time = utcnow()
        if (not force) and (_check_time < self._last_check_time + timedelta(seconds = 5)):
            _LOGGER.debug("update run only once per 5 seconds")
            return
        self._last_check_time = _check_time
        self._update()
        return

    def sendpacket(self, switch_id, packet, retry=2):
        """Send packet to device."""
        try:
            self.set_power(switch_id, packet)
            self._connected = True
        except (socket.timeout, ValueError) as error:
            if retry < 1:
                self._connected = False
                _LOGGER.error(error)
                return False
            if not self._auth():
                self._connected = False
                return False
            return self._sendpacket(packet, retry-1)
        return True

    @property
    def state(self):
        return self._state


class BroadlinkMP1Switch(SwitchDevice):
    """Representation of an Broadlink switch."""

    def __init__(self, switch_id, alias, device):
        """Initialize the switch."""
        self._id = switch_id
        self._strid = 's' + str(switch_id)
        self._name = alias
        self._state = False
        self._force = False
        self._device = device
        self._command_on = 1
        self._command_off = 0

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name
	
    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return False

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    def turn_on(self, **kwargs):
        """Turn the device on."""
        if self._device.sendpacket(self._id, self._command_on):
            self._state = True
            self._force = True
            self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn the device off."""
        if self._device.sendpacket(self._id, self._command_off):
            self._state = False
            self._force = True
            self.schedule_update_ha_state()

    def update(self):
        """Synchronize state with switch."""
        self._device.update(self._force)
        self._force = False
        self._state = self._device.state[self._strid]


