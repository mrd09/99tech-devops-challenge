// Associate on viewer-request of the SPA default behavior, not /api/*.
// CloudFront runtime: cloudfront-js-2.0. SPA router base is /.
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    if (uri === '/api' || uri.indexOf('/api/') === 0 || uri.indexOf('/releases/') === 0) {
        return request;
    }
    var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
    if (uri === '/' || lastSegment.indexOf('.') === -1) {
        request.uri = '/index.html';
    }
    return request;
}
