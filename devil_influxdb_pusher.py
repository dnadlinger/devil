#!/usr/bin/env python3
#
# Pushes stream channel statistics to InfluxDB.
#
# Qt is only used here because we already have the networking implementation
# from the GUI client.
#

from devil.evil2channel import Evil2Channel
import fliquer
import influxdb
import msgpack
import numpy as np
import zmq
from PyQt4 import QtCore as QtC

STREAMS_TO_LOG = {0: 'in_error', 1: 'out_control'}

SAMPLE_WINDOW_SIZE = 2**16


class Pusher:
    def __init__(self, db, channel, on_disconnect):
        self._db = db

        self._channel = channel
        channel.connection_ready.connect(self._setup_streams)
        channel.stream_packet_received.connect(self._got_packet)
        channel.connection_failed.connect(self._channel_failed)
        channel.shutting_down.connect(self._channel_shutdown)

        self._buffers = {}
        for k in STREAMS_TO_LOG:
            self._buffers[k] = np.array([], dtype=np.int16)

        self._on_disconnect = on_disconnect

    def _setup_streams(self):
        for k in STREAMS_TO_LOG:
            self._channel.add_stream_subscription(k)

    def _got_packet(self, packet):
        idx = packet.stream_idx
        if not idx in STREAMS_TO_LOG:
            return
        self._buffers[idx] = np.append(self._buffers[idx], packet.samples)
        self._push_if_full(idx)

    def _push_if_full(self, idx):
        buf = self._buffers[idx]
        if np.size(buf) < SAMPLE_WINDOW_SIZE:
            return

        data = buf[:SAMPLE_WINDOW_SIZE]

        self._db.write_points([{
            'measurement': STREAMS_TO_LOG[idx],
            'tags': {
                'dev_id': self._channel.resource.dev_id,
                'display_name': self._channel.resource.display_name
            },
            'fields': {
                'min': np.min(data),
                'p20': np.percentile(data, 20),
                'mean': np.mean(data),
                'p80': np.percentile(data, 80),
                'max': np.max(data)
            }
        }])

        self._buffers[idx] = buf[SAMPLE_WINDOW_SIZE:]

    def _channel_failed(self, msg):
        QtC.qWarning(' :: Channel "{}" failed: {}'.format(
            self._channel.resource.display_name, msg))
        self._on_disconnect()

    def _channel_shutdown(self):
        QtC.qWarning(' :: Channel "{}" shutting down'.format(
            self._channel.resource.display_name))
        self._on_disconnect()


def fetch_from_env(var_name, description):
    import os
    value = os.environ.get(var_name)
    if not value:
        print('{} not configured, set the "{}" environment variable.'.format(
            description, var_name))
        sys.exit(1)


if __name__ == '__main__':
    import sys

    DB_HOST = 'hydrogen.ethz.ch'
    DB_PORT = 8086
    DB_DATABASE = 'tiqi'
    DB_USER = fetch_from_env('DEVIL_INFLUXDB_USER', 'InfluxDB user name')
    DB_PASSWORD = fetch_from_env('DEVIL_INFLUXDB_PASSWORD',
                                 'InfluxDB password')

    app = QtC.QCoreApplication(sys.argv)
    db = influxdb.InfluxDBClient(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD,
                                 DB_DATABASE)
    zmq_ctx = zmq.Context()
    node = fliquer.Node()
    channels_for_dev_ids = {}

    def new_resource(host, resource):
        if resource.dev_type != 'tiqi.devil.channel':
            return

        # Close all the existing channels, if any.
        nid = resource.dev_id
        c = channels_for_dev_ids.get(nid, None)
        if c:
            QtC.qDebug(' :: Ignoring channel {}, already registered'.format(
                nid))
            return

        QtC.qDebug(' :: Discovered new channel: {}'.format(resource))

        if resource.version.major != 2:
            QtC.qWarning(' :: Ignoring EVIL version {} @ {} ({})'.format(
                resource.version, host, resource.display_name))
            return

        def on_disconnect():
            channels_for_dev_ids.pop(nid)
            node.broadcast_enumeration_request()

        channels_for_dev_ids[nid] = Pusher(db, Evil2Channel(zmq_ctx, host,
                                                            resource),
                                           on_disconnect)

    node.new_remote_resource.connect(new_resource)

    sys.exit(app.exec_())
