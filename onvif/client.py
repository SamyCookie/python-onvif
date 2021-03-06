""" ONVIF API
"""
import logging
from datetime import datetime
from os import environ
from pathlib import Path
from threading import RLock

from zeep.asyncio import AsyncTransport
from zeep.client import Client, Settings
from zeep.wsse.username import UsernameToken
import zeep.helpers

from .exceptions import ONVIFError
from .definition import SERVICES

logger = logging.getLogger('onvif')
logging.basicConfig(level=logging.INFO)
logging.getLogger('zeep.client').setLevel(logging.CRITICAL)


# Ensure methods to raise an ONVIFError Exception
# when some thing was wrong
def safeFunc(func):
    """ wrap and transform exception
    """
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as err:
            raise ONVIFError(err)
    return wrapped


class UsernameDigestTokenDtDiff(UsernameToken):
    """
    UsernameDigestToken class, with a time offset parameter that can be adjusted;
    This allows authentication on cameras without being time synchronized.
    Please note that using NTP on both end is the recommended solution,
    this should only be used in "safe" environments.
    """
    def __init__(self, user, passw, dt_diff=None, **kwargs):
        super().__init__(user, passw, **kwargs)
        self.dtDiff = dt_diff  # Date/time difference in datetime.timedelta
    
    def apply(self, envelope, headers):
        oldCreated = self.created
        if self.created is None:
            self.created = datetime.utcnow()
        if self.dtDiff is not None:
            self.created += self.dtDiff
        result = super().apply(envelope, headers)
        self.created = oldCreated
        return result


class ONVIFService:
    """
    Python Implemention for ONVIF Service.
    Services List:
        DeviceMgmt DeviceIO Event AnalyticsDevice Display Imaging Media
        PTZ Receiver RemoteDiscovery Recording Replay Search Extension

    >>> from onvif import ONVIFService
    >>> device_service = ONVIFService('http://192.168.0.112/onvif/device_service',
    ...                           'admin', 'foscam',
    ...                           '/etc/onvif/wsdl/devicemgmt.wsdl')
    >>> ret = device_service.GetHostname()
    >>> print ret.FromDHCP
    >>> print ret.Name
    >>> device_service.SetHostname(dict(Name='newhostname'))
    >>> ret = device_service.GetSystemDateAndTime()
    >>> print ret.DaylightSavings
    >>> print ret.TimeZone
    >>> dict_ret = device_service.to_dict(ret)
    >>> print dict_ret['TimeZone']

    There are two ways to pass parameter to services methods
    1. Dict
        params = {'Name': 'NewHostName'}
        device_service.SetHostname(params)
    2. Type Instance
        params = device_service.create_type('SetHostname')
        params.Hostname = 'NewHostName'
        device_service.SetHostname(params)
    """
    @safeFunc
    def __init__(self, xaddr, wsse: UsernameDigestTokenDtDiff, url: Path, *,
                 bindingName='', transport=None):
        if not url.is_file():
            raise ONVIFError('%s doesn`t exist!' % url)
        
        self.url = url
        self.xaddr = xaddr
        
        if not transport:
            transport = AsyncTransport(None)
        self.client = Client(wsdl=str(url), wsse=wsse, transport=transport,
                             settings=Settings(strict=False, xml_huge_tree=True))
        self.wsClient = self.client.create_service(bindingName, xaddr)
        self.bindingName = bindingName
    
    def createType(self, name):
        """ create type
        """
        bindingName = self.bindingName
        namespace = bindingName[bindingName.find('{')+1:bindingName.find('}')]
        client = self.client
        availableNs = client.namespaces
        ns = list(availableNs.keys())[list(availableNs.values()).index(namespace)]
        return client.get_element((ns or 'ns0') + ':' + name)()
    
    @staticmethod
    @safeFunc
    def to_dict(zeepobject):
        # Convert a WSDL Type instance into a dictionary
        return {} if zeepobject is None else zeep.helpers.serialize_object(zeepobject)
    
    @classmethod
    def service_wrapper(cls, func):
        @safeFunc
        def wrapped(params=None):
            params = {} if params is None else cls.to_dict(params)
            try:
                ret = func(**params)
            except TypeError:
                ret = func(params)
            return ret
        return wrapped
    
    def __getattr__(self, name):
        """
        Call the real onvif Service operations,
        See the official wsdl definition for the
        APIs detail(API name, request parameters,
        response parameters, parameter types, etc...)
        """
        builtin = name.startswith('__') and name.endswith('__')
        if builtin:
            return self.__dict__[name]
        else:
            return self.service_wrapper(getattr(self.wsClient, name))


class ONVIFCamera:
    """
    Python Implementation of an ONVIF compliant device.
    This class integrates ONVIF services

    adjust_time parameter allows authentication on cameras
    without being time synchronized.
    Please note that using NTP on both end is the recommended solution,
    this should only be used in "safe" environments.
    Also, this cannot be used on AXIS camera, as every request is authenticated,
    contrary to ONVIF standard

    >>> from onvif import ONVIFCamera
    >>> mycam = ONVIFCamera('192.168.0.112', 80, 'admin', '12345')
    >>> mycam.devicemgmt.GetServices(False)
    >>> media_service = mycam.createService('media')
    >>> ptz_service = mycam.create_service('ptz')
    # Get PTZ Configuration:
    >>> ptz_service.GetConfiguration()
    """
    PullPointSubscription = 'http://www.onvif.org/ver10/events/wsdl/PullPointSubscription'
    
    def __init__(self, host, port, user, passwd,
                 wsdlDir: Path=Path(__file__).parent.parent/'wsdl',
                 encrypt=True, adjust_time=False, transport=None):
        environ.pop('http_proxy', None)
        environ.pop('https_proxy', None)
        self.host = host
        self.port = int(port)
        self.user = user
        self.passwd = passwd
        self.wsdlDir = wsdlDir
        self.encrypt = encrypt
        self.adjustTime = adjust_time
        self.transport = transport
        self.xaddrs = { }
        self.wsse = None
        
        # Active service client container
        self.services = {}
        self.servicesLock = RLock()
        
    
    toDict = ONVIFService.to_dict
    
    async def update_xaddrs(self):
        # Establish devicemgmt service first
        devicemgmt = self.getService('devicemgmt')
        if self.adjustTime:
            cdate = await devicemgmt.GetSystemDateAndTime().UTCDateTime
            camDate = datetime(cdate.Date.Year, cdate.Date.Month, cdate.Date.Day,
                               cdate.Time.Hour, cdate.Time.Minute, cdate.Time.Second)
            dtDiff = camDate - datetime.utcnow()
            self.wsse = UsernameDigestTokenDtDiff(self.user, self.passwd,
                                                  dt_diff=dtDiff, use_digest=self.encrypt)
            devicemgmt = self.createService('devicemgmt')
        # Get XAddr of services on the device
        self.xaddrs = {}
        capabilities = await devicemgmt.GetCapabilities({'Category': 'All'})
        for name in capabilities:
            capability = capabilities[name]
            try:
                serviceInfo = SERVICES.get(name.lower())
                if serviceInfo is not None and capability is not None:
                    self.xaddrs[serviceInfo.ns] = capability['XAddr']
            except Exception:
                logger.exception('Unexpected service type')
        
        with self.servicesLock:
            try:
                events = self.getService('events')
                pullpoint = await events.CreatePullPointSubscription()
                self.xaddrs[self.PullPointSubscription] = \
                    pullpoint.SubscriptionReference.Address._value_1  #pylint: disable=protected-access
            except Exception:
                pass

    async def update_url(self, host=None, port=None):
        changed = False
        if host and self.host != host:
            changed = True
            self.host = host
        if port and self.port != port:
            changed = True
            self.port = port
        
        if not changed:
            return
        
        devicemgmt = self.getService('devicemgmt')
        capabilities = await devicemgmt.GetCapabilities()
        
        with self.servicesLock:
            for sname, service in self.services.items():
                xaddr = getattr(capabilities, sname).XAddr
                await service.wsClient.set_options(location=xaddr)
    
    def getService(self, name, create=True):
        """ get (and maybe created) service from cache
        """
        name = name.lower()
        try:
            service = self.services[name]
        except KeyError:
            if not create:
                raise ONVIFError("service '%s' has not been created" % name)
            service = self.createService(name)
        return service
    
    def getDefinition(self, name):
        """Returns xaddr and wsdl of specified service
        """
        serviceInfo = SERVICES.get(name)
        if serviceInfo is None:
            raise ONVIFError('Unknown service %s' % name)
        
        ns, wsdlFilename, binding, portType = serviceInfo
        bindingName = '{%s}%s' % (ns, binding)
        if portType is not None:
            ns += '/' + portType
        
        # XAddr for devicemgmt is fixed:
        if name == 'devicemgmt':
            xaddr = self.host
            if not (xaddr.startswith('http://') or xaddr.startswith('https://')):
                xaddr = 'http://%s' % xaddr
            xaddr = '%s:%s/onvif/device_service' % (xaddr, self.port)
        else:
            # Get other XAddr
            xaddr = self.xaddrs.get(ns)
            if not xaddr:
                raise ONVIFError("Device doesn't support service: %s" % name)
        return xaddr, wsdlFilename, bindingName

    def createService(self, name, transport=None):
        """
        Create ONVIF service client.

        :param name: service name, should be present as a key within
        the `SERVICES` dictionary declared within the `onvif.definition` module
        :param portType:
        :param transport:
        :return:
        """
        name = name.lower()
        xaddr, wsdlFilename, bindingName = self.getDefinition(name)
        with self.servicesLock:
            if not transport:
                transport = self.transport
            self.services[name] = service = \
                ONVIFService(xaddr, self.wsse, self.wsdlDir/wsdlFilename,
                             bindingName=bindingName, transport=transport)
        return service
