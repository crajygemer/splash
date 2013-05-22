import time, resource, json
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor, defer
from twisted.python import log
from splash2.qtrender import HtmlRender, PngRender, RenderError
from splash2.utils import getarg, BadRequest


class RenderHtml(Resource):

    isLeaf = True
    content_type = "text/html; charset=utf-8"

    def _getRender(self, request):
        url = getarg(request, "url")
        baseurl = getarg(request, "baseurl", None)
        return HtmlRender(url, baseurl)

    def render_GET(self, request):
        render = self._getRender(request)
        d = render.deferred
        timeout = getarg(request, "timeout", 30, type=float)
        timer = reactor.callLater(timeout, d.cancel)
        d.addCallback(self._cancelTimer, timer)
        d.addCallback(self._writeOutput, request)
        d.addErrback(self._timeoutError, request)
        d.addErrback(self._renderError, request)
        d.addErrback(self._internalError, request)
        d.addBoth(self._finishRequest, request)
        request.starttime = time.time()
        return NOT_DONE_YET

    def render(self, request):
        try:
            return Resource.render(self, request)
        except BadRequest as e:
            request.setResponseCode(400)
            return str(e) + "\n"

    def _cancelTimer(self, _, timer):
        timer.cancel()
        return _

    def _writeOutput(self, html, request):
        stats = {
            "path": request.path,
            "args": request.args,
            "rendertime": time.time() - request.starttime,
            "rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        log.msg(json.dumps(stats), system="stats")
        request.setHeader("content-type", self.content_type)
        request.write(html)

    def _timeoutError(self, failure, request):
        failure.trap(defer.CancelledError)
        request.setResponseCode(504)
        request.write("Timeout exceeded rendering page\n")

    def _renderError(self, failure, request):
        failure.trap(RenderError)
        request.setResponseCode(502)
        request.write("Error rendering page\n")

    def _internalError(self, failure, request):
        request.setResponseCode(500)
        request.write(failure.getErrorMessage())
        log.err()

    def _finishRequest(self, _, request):
        if not request._disconnected:
            request.finish()


class RenderPng(RenderHtml):

    content_type = "image/png"

    def _getRender(self, request):
        url = getarg(request, "url")
        baseurl = getarg(request, "baseurl", None)
        width = getarg(request, "width", None, type=int)
        height = getarg(request, "height", None, type=int)
        return PngRender(url, baseurl, width, height)


class Root(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.putChild("render.html", RenderHtml())
        self.putChild("render.png", RenderPng())

    def getChild(self, name, request):
        if name == "":
            return self
        return Resource.getChild(self, name, request)

    def render_GET(self, request):
        return ""
