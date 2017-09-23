
import urllib
import logging
import functools
import xmltodict

from flask import request, url_for
from wechatpy.component import ComponentVerifyTicketMessage
from wechatpy.component import ComponentUnauthorizedMessage
from wechatpy.crypto import PrpCrypto
from wechatpy.utils import to_text
from wechatpy import parse_message, create_reply

from base import WeChatBase


class Component(WeChatBase):

    def authcall_url(self, pre_auth_code, redirect_uri):
        """
        url for component authorization.

        param: pre_auth_code: string: pre_auth_code for component.
        param: redirect_url : string: auth result redirect url.

        return: url for auth
        """
        urls = [
            'https://mp.weixin.qq.com/cgi-bin/',
            'componentloginpage?',
            'component_appid=',
            self.component_appid,
            '&pre_auth_code=',
            pre_auth_code,
            '&redirect_uri=',
            redirect_uri
        ]
        return ''.join(urls)

    def component_notify(self):
        """
        receive component ticket and unauthorized message.
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kw):
                logging.debug('wechat component called.')
                data = xmltodict.parse(to_text(request.data))['xml']

                appid = str(data.get('AppId'))
                encrypt = str(data.get('Encrypt'))
                if not appid == self.component_appid:
                    return 'fail'

                decrypt = PrpCrypto(self.crypto.key).decrypt(encrypt, self.crypto._id)

                message = xmltodict.parse(to_text(decrypt))['xml']
                if message.get('InfoType') == ComponentVerifyTicketMessage.type:
                    logging.debug('receive wechat component ticket message.')
                    o = ComponentVerifyTicketMessage(message)
                    self.session.set(o.type, o.verify_ticket, 600)
                    logging.debug('update component ticket success: {}'.format(self.component_verify_ticket))

                elif message.get('InfoType') == ComponentUnauthorizedMessage.type:
                    pass

                res = func(*args, **kw)
                if res and res.lower() != 'success':
                    return 'fail'
                return 'success'

            return wrapper
        return decorator

    def component_authcall(self, callback_endpoint, **callback_params):
        """
        decorator for component authorization router.
        create pre_auth_code to start request and response to callback url.

        request.wechat_msg.get("component_auth_url") for authorization url.

        param: callback_endpoint: string: endpoint of callback url.
        param: **callback_params: params for callback endpoint.
        """

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kw):
                preauthcode = self.create_preauthcode().get('pre_auth_code')
                redirect_url = url_for(callback_endpoint, **callback_params)
                redirect_url = urllib.quote_plus(request.url_root[:-1] + redirect_url)
                url = self.authcall_url(preauthcode, redirect_url)
                request.wechat_msg = {'component_authcall_url': url}
                return func(*args, **kw)

            return wrapper
        return decorator

    def component_authcallback(self):
        """
        decorator for component authorization callback router.

        request.wechat_smg.get("component_client") for WeChatComponentClient object.
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kw):
                auth_code = str(request.args.get('auth_code'))
                client = self.get_client_by_authorization_code(auth_code)
                request.wechat_msg = {'component_client': client}
                return func(*args, **kw)

            return wrapper
        return decorator

    def component_mp_notify(self):
        """
        decorator for component authorized mp notify router.
        decrypt message and encrypt the response of router function.

        request.wechat_msg.get("component_mp_notify")
        request.wechat_msg.get("component_client")
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kw):
                logging.debug('receive component mp notify: {}'.format(request.data))
                data = xmltodict.parse(to_text(request.data))['xml']
                signature = request.args.get('msg_signature')
                timestamp = request.args.get('timestamp')
                nonce = request.args.get('nonce')

                message = self.crypto.decrypt_message(data, signature, timestamp, nonce)
                message = parse_message(message)
                client = self.get_client_by_appid(kw.get('appid'))

                request.wechat_msg = {
                    'component_mp_notify': message.content,
                    'component_client': client
                }
                res = func(*args, **kw)
                res_data = str(create_reply(res, message=message, render=True))
                return self.crypto.encrypt_message(res_data, nonce, timestamp)

            return wrapper
        return decorator
