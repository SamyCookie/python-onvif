""" ONVIF API
"""
import logging
from datetime import datetime
from os import environ, path
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
    def __init__(self, xaddr, user, passwd, url, *,
                 encrypt=True, dt_diff=None, binding_name='', transport=None):
        if not path.isfile(url):
            raise ONVIFError('%s doesn`t exist!' % url)
        
        self.url = url
        self.xaddr = xaddr
        wsse = UsernameDigestTokenDtDiff(user, passwd, dt_diff=dt_diff, use_digest=encrypt)
        # Create soap client
        if not transport:
            transport = AsyncTransport(None)
        settings = Settings()
        settings.strict = False
        settings.xml_huge_tree = True
        self.zeep_client = zeep_client = \
            Client(wsdl=url, wsse=wsse, transport=transport, settings=settings)
        self.ws_client = zeep_client.create_service(binding_name, self.xaddr)
        
        # Set soap header for authentication
        self.user = user
        self.passwd = passwd
        # Indicate wether password digest is needed
        self.encrypt = encrypt
        self.dt_diff = dt_diff
        
        namespace = binding_name[binding_name.find('{')+1:binding_name.find('}')]
        available_ns = zeep_client.namespaces
        ns = list(available_ns.keys())[list(available_ns.values()).index(namespace)] or 'ns0'
        self.create_type = lambda x: zeep_client.get_element(ns + ':' + x)()
    
    @classmethod
    @safeFunc
    def clone(cls, service, *args, **kwargs):
        clone_service = service.ws_client.clone()
        kwargs['ws_client'] = clone_service
        return ONVIFService(*args, **kwargs)
    
    @staticmethod
    @safeFunc
    def to_dict(zeepobject):
        # Convert a WSDL Type instance into a dictionary
        return {} if zeepobject is None else zeep.helpers.serialize_object(zeepobject)
    
    def service_wrapper(self, func):
        @safeFunc
        def wrapped(params=None):
            def call(params=None):
                # No params
                # print(params.__class__.__mro__)
                if params is None:
                    params = {}
                else:
                    params = ONVIFService.to_dict(params)
                try:
                    ret = func(**params)
                except TypeError:
                    ret = func(params)
                return ret
            
            return call(params)
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
            return self.service_wrapper(getattr(self.ws_client, name))


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
                 wsdl_dir=path.join(path.dirname(path.dirname(__file__)), 'wsdl'),
                 encrypt=True, adjust_time=False, transport=None):
        environ.pop('http_proxy', None)
        environ.pop('https_proxy', None)
        self.host = host
        self.port = int(port)
        self.user = user
        self.passwd = passwd
        self.wsdl_dir = wsdl_dir
        self.encrypt = encrypt
        self.adjust_time = adjust_time
        self.transport = transport
        self.dt_diff = None
        self.xaddrs = { }
        
        # Active service client container
        self.services = {}
        self.services_lock = RLock()
        
        self.to_dict = ONVIFService.to_dict
    
    async def update_xaddrs(self):
        # Establish devicemgmt service first
        self.dt_diff = None
        self.devicemgmt = self.createService('devicemgmt')
        if self.adjust_time:
            cdate = await self.devicemgmt.GetSystemDateAndTime().UTCDateTime
            cam_date = datetime(cdate.Date.Year, cdate.Date.Month, cdate.Date.Day,
                                   cdate.Time.Hour, cdate.Time.Minute, cdate.Time.Second)
            self.dt_diff = cam_date - datetime.utcnow()
            self.devicemgmt = self.createService('devicemgmt')
        # Get XAddr of services on the device
        self.xaddrs = {}
        capabilities = await self.devicemgmt.GetCapabilities({'Category': 'All'})
        for name in capabilities:
            capability = capabilities[name]
            try:
                if name.lower() in SERVICES and capability is not None:
                    ns = SERVICES[name.lower()]['ns']
                    self.xaddrs[ns] = capability['XAddr']
            except Exception:
                logger.exception('Unexpected service type')
        
        with self.services_lock:
            try:
                self.event = self.createService('events')
                pullpoint = await self.event.CreatePullPointSubscription()
                self.xaddrs[self.PullPointSubscription] = \
                    pullpoint.SubscriptionReference.Address._value_1
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
        
        self.devicemgmt = self.createService('devicemgmt')
        self.capabilities = await self.devicemgmt.GetCapabilities()
        
        with self.services_lock:
            for sname in self.services.keys():
                xaddr = getattr(self.capabilities, sname.capitalize).XAddr
                await self.services[sname].ws_client.set_options(location=xaddr)
    
    def get_service(self, name, create=True):
        service = getattr(self, name.lower(), None)
        if not service and create:
            return self.createService(name.lower())
        return service
    
    def get_definition(self, name, portType=None):
        """Returns xaddr and wsdl of specified service"""
        # Check if the service is supported
        if name not in SERVICES:
            raise ONVIFError('Unknown service %s' % name)
        wsdl_file = SERVICES[name]['wsdl']
        ns = SERVICES[name]['ns']
        
        binding_name = '{%s}%s' % (ns, SERVICES[name]['binding'])
        
        if portType:
            ns += '/' + portType
        
        wsdlpath = path.join(self.wsdl_dir, wsdl_file)
        if not path.isfile(wsdlpath):
            raise ONVIFError('No such file: %s' % wsdlpath)
        
        # XAddr for devicemgmt is fixed:
        if name == 'devicemgmt':
            xaddr = self.host
            if not (xaddr.startswith('http://') or xaddr.startswith('https://')):
                xaddr = 'http://%s' % xaddr
            xaddr = '%s:%s/onvif/device_service' % (xaddr, self.port)
            return xaddr, wsdlpath, binding_name
        
        # Get other XAddr
        xaddr = self.xaddrs.get(ns)
        if not xaddr:
            raise ONVIFError("Device doesn't support service: %s" % name)
        
        return xaddr, wsdlpath, binding_name

    def createService(self, name, portType=None, transport=None):
        """
        Create ONVIF service client.

        :param name: service name, should be present as a key within
        the `SERVICES` dictionary declared within the `onvif.definition` module
        :param portType:
        :param transport:
        :return:
        """
        name = name.lower()
        xaddr, wsdlFile, bindingName = self.get_definition(name, portType)
        with self.services_lock:
            if not transport:
                transport = self.transport
            service = ONVIFService(xaddr, self.user, self.passwd, wsdlFile,
                                   encrypt=self.encrypt,
                                   dt_diff=self.dt_diff,
                                   binding_name=bindingName,
                                   transport=transport)
            self.services[name] = service
            setattr(self, name, service)
        return service
