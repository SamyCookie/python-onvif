""" definition file
"""
from collections import namedtuple

NS = 'http://www.onvif.org/'
SI = namedtuple('ServiceInfo', ('ns', 'wsdl', 'binding'))

SERVICES = {
    'devicemgmt'   : SI(NS+'ver10/device/wsdl', 'devicemgmt.wsdl', 'DeviceBinding'),
    'media'        : SI(NS+'ver10/media/wsdl',     'media.wsdl',     'MediaBinding'),
    'ptz'          : SI(NS+'ver20/ptz/wsdl',       'ptz.wsdl',       'PTZBinding'),
    'imaging'      : SI(NS+'ver20/imaging/wsdl',   'imaging.wsdl',   'ImagingBinding'),
    'deviceio'     : SI(NS+'ver10/deviceIO/wsdl',  'deviceio.wsdl',  'DeviceIOBinding'),
    'events'       : SI(NS+'ver10/events/wsdl',    'events.wsdl',    'EventBinding'),
    'pullpoint'    : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'PullPointSubscriptionBinding'),
    'notification' : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'NotificationProducerBinding'),
    'subscription' : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'SubscriptionManagerBinding'),
    'analytics'    : SI(NS+'ver20/analytics/wsdl', 'analytics.wsdl',
                        'AnalyticsEngineBinding'),
    'recording'    : SI(NS+'ver10/recording/wsdl', 'recording.wsdl', 'RecordingBinding'),
    'search'       : SI(NS+'ver10/search/wsdl',    'search.wsdl',    'SearchBinding'),
    'replay'       : SI(NS+'ver10/replay/wsdl',    'replay.wsdl',    'ReplayBinding'),
    'receiver'     : SI(NS+'ver10/receiver/wsdl',  'receiver.wsdl',  'ReceiverBinding'),
}
