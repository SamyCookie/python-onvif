""" definition file
"""
from collections import namedtuple

NS = 'http://www.onvif.org/'
SI = namedtuple('ServiceInfo', ('ns', 'wsdl', 'binding', 'portType'))

SERVICES = {
    'devicemgmt'   : SI(NS+'ver10/device/wsdl', 'devicemgmt.wsdl', 'DeviceBinding', None),
    'media'        : SI(NS+'ver10/media/wsdl',     'media.wsdl', 'MediaBinding', None),
    'ptz'          : SI(NS+'ver20/ptz/wsdl',       'ptz.wsdl',   'PTZBinding', None),
    'imaging'      : SI(NS+'ver20/imaging/wsdl', 'imaging.wsdl', 'ImagingBinding', None),
    'deviceio'     : SI(NS+'ver10/deviceIO/wsdl', 'deviceio.wsdl',
                        'DeviceIOBinding', None),
    'events'       : SI(NS+'ver10/events/wsdl',    'events.wsdl',  'EventBinding', None),
    'pullpoint'    : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'PullPointSubscriptionBinding', 'PullPointSubscription'),
    'notification' : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'NotificationProducerBinding', None),
    'subscription' : SI(NS+'ver10/events/wsdl',    'events.wsdl',
                        'SubscriptionManagerBinding', None),
    'analytics'    : SI(NS+'ver20/analytics/wsdl', 'analytics.wsdl',
                        'AnalyticsEngineBinding', None),
    'recording'    : SI(NS+'ver10/recording/wsdl', 'recording.wsdl',
                        'RecordingBinding', None),
    'search'       : SI(NS+'ver10/search/wsdl',    'search.wsdl', 'SearchBinding', None),
    'replay'       : SI(NS+'ver10/replay/wsdl',    'replay.wsdl', 'ReplayBinding', None),
    'receiver'     : SI(NS+'ver10/receiver/wsdl', 'receiver.wsdl',
                        'ReceiverBinding', None),
}
