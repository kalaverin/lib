# ruff: noqa: N818,N802,PIE794,A001  # leaf aliases shadow builtins by contract

from __future__ import annotations

from collections.abc import Iterable
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, override

if TYPE_CHECKING:
    from zx.lib.hypertext.response.core import Response

ExpectedStatus = HTTPStatus | int | Iterable[HTTPStatus | int] | None

__all__ = (
    "ClientError",
    "ExpectedStatus",
    "HTTPError",
    "InformationalError",
    "RedirectionError",
    "ServerError",
    "SuccessfulError",
)


class HTTPError(Exception):
    status: ClassVar[HTTPStatus]

    Informational: ClassVar[type[HTTPError]]
    Successful: ClassVar[type[HTTPError]]
    Redirection: ClassVar[type[HTTPError]]
    Client: ClassVar[type[HTTPError]]
    Server: ClassVar[type[HTTPError]]
    Continue: ClassVar[type[HTTPError]]
    SwitchingProtocols: ClassVar[type[HTTPError]]
    Processing: ClassVar[type[HTTPError]]
    EarlyHints: ClassVar[type[HTTPError]]
    Ok: ClassVar[type[HTTPError]]
    Created: ClassVar[type[HTTPError]]
    Accepted: ClassVar[type[HTTPError]]
    NonAuthoritativeInformation: ClassVar[type[HTTPError]]
    NoContent: ClassVar[type[HTTPError]]
    ResetContent: ClassVar[type[HTTPError]]
    PartialContent: ClassVar[type[HTTPError]]
    MultiStatus: ClassVar[type[HTTPError]]
    AlreadyReported: ClassVar[type[HTTPError]]
    ImUsed: ClassVar[type[HTTPError]]
    MultipleChoices: ClassVar[type[HTTPError]]
    MovedPermanently: ClassVar[type[HTTPError]]
    Found: ClassVar[type[HTTPError]]
    SeeOther: ClassVar[type[HTTPError]]
    NotModified: ClassVar[type[HTTPError]]
    UseProxy: ClassVar[type[HTTPError]]
    TemporaryRedirect: ClassVar[type[HTTPError]]
    PermanentRedirect: ClassVar[type[HTTPError]]
    BadRequest: ClassVar[type[HTTPError]]
    Unauthorized: ClassVar[type[HTTPError]]
    PaymentRequired: ClassVar[type[HTTPError]]
    Forbidden: ClassVar[type[HTTPError]]
    NotFound: ClassVar[type[HTTPError]]
    MethodNotAllowed: ClassVar[type[HTTPError]]
    NotAcceptable: ClassVar[type[HTTPError]]
    ProxyAuthenticationRequired: ClassVar[type[HTTPError]]
    RequestTimeout: ClassVar[type[HTTPError]]
    Conflict: ClassVar[type[HTTPError]]
    Gone: ClassVar[type[HTTPError]]
    LengthRequired: ClassVar[type[HTTPError]]
    PreconditionFailed: ClassVar[type[HTTPError]]
    RequestEntityTooLarge: ClassVar[type[HTTPError]]
    RequestUriTooLong: ClassVar[type[HTTPError]]
    UnsupportedMediaType: ClassVar[type[HTTPError]]
    RequestedRangeNotSatisfiable: ClassVar[type[HTTPError]]
    ExpectationFailed: ClassVar[type[HTTPError]]
    ImATeapot: ClassVar[type[HTTPError]]
    MisdirectedRequest: ClassVar[type[HTTPError]]
    UnprocessableEntity: ClassVar[type[HTTPError]]
    Locked: ClassVar[type[HTTPError]]
    FailedDependency: ClassVar[type[HTTPError]]
    TooEarly: ClassVar[type[HTTPError]]
    UpgradeRequired: ClassVar[type[HTTPError]]
    PreconditionRequired: ClassVar[type[HTTPError]]
    TooManyRequests: ClassVar[type[HTTPError]]
    RequestHeaderFieldsTooLarge: ClassVar[type[HTTPError]]
    UnavailableForLegalReasons: ClassVar[type[HTTPError]]
    InternalServerError: ClassVar[type[HTTPError]]
    NotImplemented: ClassVar[type[HTTPError]]
    BadGateway: ClassVar[type[HTTPError]]
    ServiceUnavailable: ClassVar[type[HTTPError]]
    GatewayTimeout: ClassVar[type[HTTPError]]
    HttpVersionNotSupported: ClassVar[type[HTTPError]]
    VariantAlsoNegotiates: ClassVar[type[HTTPError]]
    InsufficientStorage: ClassVar[type[HTTPError]]
    LoopDetected: ClassVar[type[HTTPError]]
    NotExtended: ClassVar[type[HTTPError]]
    NetworkAuthenticationRequired: ClassVar[type[HTTPError]]
    Continue: ClassVar[type[HTTPError]]  # 100
    SwitchingProtocols: ClassVar[type[HTTPError]]  # 101
    Processing: ClassVar[type[HTTPError]]  # 102
    EarlyHints: ClassVar[type[HTTPError]]  # 103
    Ok: ClassVar[type[HTTPError]]  # 200
    Created: ClassVar[type[HTTPError]]  # 201
    Accepted: ClassVar[type[HTTPError]]  # 202
    NonAuthoritativeInformation: ClassVar[type[HTTPError]]  # 203
    NoContent: ClassVar[type[HTTPError]]  # 204
    ResetContent: ClassVar[type[HTTPError]]  # 205
    PartialContent: ClassVar[type[HTTPError]]  # 206
    MultiStatus: ClassVar[type[HTTPError]]  # 207
    AlreadyReported: ClassVar[type[HTTPError]]  # 208
    ImUsed: ClassVar[type[HTTPError]]  # 226
    MultipleChoices: ClassVar[type[HTTPError]]  # 300
    MovedPermanently: ClassVar[type[HTTPError]]  # 301
    Found: ClassVar[type[HTTPError]]  # 302
    SeeOther: ClassVar[type[HTTPError]]  # 303
    NotModified: ClassVar[type[HTTPError]]  # 304
    UseProxy: ClassVar[type[HTTPError]]  # 305
    TemporaryRedirect: ClassVar[type[HTTPError]]  # 307
    PermanentRedirect: ClassVar[type[HTTPError]]  # 308
    BadRequest: ClassVar[type[HTTPError]]  # 400
    Unauthorized: ClassVar[type[HTTPError]]  # 401
    PaymentRequired: ClassVar[type[HTTPError]]  # 402
    Forbidden: ClassVar[type[HTTPError]]  # 403
    NotFound: ClassVar[type[HTTPError]]  # 404
    MethodNotAllowed: ClassVar[type[HTTPError]]  # 405
    NotAcceptable: ClassVar[type[HTTPError]]  # 406
    ProxyAuthenticationRequired: ClassVar[type[HTTPError]]  # 407
    RequestTimeout: ClassVar[type[HTTPError]]  # 408
    Conflict: ClassVar[type[HTTPError]]  # 409
    Gone: ClassVar[type[HTTPError]]  # 410
    LengthRequired: ClassVar[type[HTTPError]]  # 411
    PreconditionFailed: ClassVar[type[HTTPError]]  # 412
    ContentTooLarge: ClassVar[type[HTTPError]]  # 413
    UriTooLong: ClassVar[type[HTTPError]]  # 414
    UnsupportedMediaType: ClassVar[type[HTTPError]]  # 415
    RangeNotSatisfiable: ClassVar[type[HTTPError]]  # 416
    ExpectationFailed: ClassVar[type[HTTPError]]  # 417
    ImATeapot: ClassVar[type[HTTPError]]  # 418
    MisdirectedRequest: ClassVar[type[HTTPError]]  # 421
    UnprocessableContent: ClassVar[type[HTTPError]]  # 422
    Locked: ClassVar[type[HTTPError]]  # 423
    FailedDependency: ClassVar[type[HTTPError]]  # 424
    TooEarly: ClassVar[type[HTTPError]]  # 425
    UpgradeRequired: ClassVar[type[HTTPError]]  # 426
    PreconditionRequired: ClassVar[type[HTTPError]]  # 428
    TooManyRequests: ClassVar[type[HTTPError]]  # 429
    RequestHeaderFieldsTooLarge: ClassVar[type[HTTPError]]  # 431
    UnavailableForLegalReasons: ClassVar[type[HTTPError]]  # 451
    InternalServerError: ClassVar[type[HTTPError]]  # 500
    NotImplemented: ClassVar[type[HTTPError]]  # 501
    BadGateway: ClassVar[type[HTTPError]]  # 502
    ServiceUnavailable: ClassVar[type[HTTPError]]  # 503
    GatewayTimeout: ClassVar[type[HTTPError]]  # 504
    HttpVersionNotSupported: ClassVar[type[HTTPError]]  # 505
    VariantAlsoNegotiates: ClassVar[type[HTTPError]]  # 506
    InsufficientStorage: ClassVar[type[HTTPError]]  # 507
    LoopDetected: ClassVar[type[HTTPError]]  # 508
    NotExtended: ClassVar[type[HTTPError]]  # 510
    NetworkAuthenticationRequired: ClassVar[type[HTTPError]]  # 511

    @classmethod
    def by_code(cls, code: int | HTTPStatus, /) -> type[HTTPError]:
        return REGISTRY[HTTPStatus(int(code))]

    def __init__(self, response: Response[Any]) -> None:
        self.response = response
        self.reason: str = response.reason or self.status.phrase
        super().__init__(self.message)

    @property
    def message(self) -> str:
        """Human-readable one-liner: ``404 Not Found``."""
        return f"{int(self.status)} {self.reason}"

    @override
    def __str__(self) -> str:
        return self.message

    # --- range aggregates --------------------------------------------------

    @property
    def isInformational(self) -> bool:
        return bool(self.status.is_informational)

    @property
    def isSuccess(self) -> bool:
        return bool(self.status.is_success)

    @property
    def isRedirection(self) -> bool:
        return bool(self.status.is_redirection)

    @property
    def isClientError(self) -> bool:
        return bool(self.status.is_client_error)

    @property
    def isServerError(self) -> bool:
        return bool(self.status.is_server_error)

    # --- per-status checks ---------------------------------------------------

    @property
    def isContinue(self) -> bool:
        return self.status is HTTPStatus.CONTINUE

    @property
    def isSwitchingProtocols(self) -> bool:
        return self.status is HTTPStatus.SWITCHING_PROTOCOLS

    @property
    def isProcessing(self) -> bool:
        return self.status is HTTPStatus.PROCESSING

    @property
    def isEarlyHints(self) -> bool:
        return self.status is HTTPStatus.EARLY_HINTS

    @property
    def isOk(self) -> bool:
        return self.status is HTTPStatus.OK

    @property
    def isCreated(self) -> bool:
        return self.status is HTTPStatus.CREATED

    @property
    def isAccepted(self) -> bool:
        return self.status is HTTPStatus.ACCEPTED

    @property
    def isNonAuthoritativeInformation(self) -> bool:
        return self.status is HTTPStatus.NON_AUTHORITATIVE_INFORMATION

    @property
    def isNoContent(self) -> bool:
        return self.status is HTTPStatus.NO_CONTENT

    @property
    def isResetContent(self) -> bool:
        return self.status is HTTPStatus.RESET_CONTENT

    @property
    def isPartialContent(self) -> bool:
        return self.status is HTTPStatus.PARTIAL_CONTENT

    @property
    def isMultiStatus(self) -> bool:
        return self.status is HTTPStatus.MULTI_STATUS

    @property
    def isAlreadyReported(self) -> bool:
        return self.status is HTTPStatus.ALREADY_REPORTED

    @property
    def isImUsed(self) -> bool:
        return self.status is HTTPStatus.IM_USED

    @property
    def isMultipleChoices(self) -> bool:
        return self.status is HTTPStatus.MULTIPLE_CHOICES

    @property
    def isMovedPermanently(self) -> bool:
        return self.status is HTTPStatus.MOVED_PERMANENTLY

    @property
    def isFound(self) -> bool:
        return self.status is HTTPStatus.FOUND

    @property
    def isSeeOther(self) -> bool:
        return self.status is HTTPStatus.SEE_OTHER

    @property
    def isNotModified(self) -> bool:
        return self.status is HTTPStatus.NOT_MODIFIED

    @property
    def isUseProxy(self) -> bool:
        return self.status is HTTPStatus.USE_PROXY

    @property
    def isTemporaryRedirect(self) -> bool:
        return self.status is HTTPStatus.TEMPORARY_REDIRECT

    @property
    def isPermanentRedirect(self) -> bool:
        return self.status is HTTPStatus.PERMANENT_REDIRECT

    @property
    def isBadRequest(self) -> bool:
        return self.status is HTTPStatus.BAD_REQUEST

    @property
    def isUnauthorized(self) -> bool:
        return self.status is HTTPStatus.UNAUTHORIZED

    @property
    def isPaymentRequired(self) -> bool:
        return self.status is HTTPStatus.PAYMENT_REQUIRED

    @property
    def isForbidden(self) -> bool:
        return self.status is HTTPStatus.FORBIDDEN

    @property
    def isNotFound(self) -> bool:
        return self.status is HTTPStatus.NOT_FOUND

    @property
    def isMethodNotAllowed(self) -> bool:
        return self.status is HTTPStatus.METHOD_NOT_ALLOWED

    @property
    def isNotAcceptable(self) -> bool:
        return self.status is HTTPStatus.NOT_ACCEPTABLE

    @property
    def isProxyAuthenticationRequired(self) -> bool:
        return self.status is HTTPStatus.PROXY_AUTHENTICATION_REQUIRED

    @property
    def isRequestTimeout(self) -> bool:
        return self.status is HTTPStatus.REQUEST_TIMEOUT

    @property
    def isConflict(self) -> bool:
        return self.status is HTTPStatus.CONFLICT

    @property
    def isGone(self) -> bool:
        return self.status is HTTPStatus.GONE

    @property
    def isLengthRequired(self) -> bool:
        return self.status is HTTPStatus.LENGTH_REQUIRED

    @property
    def isPreconditionFailed(self) -> bool:
        return self.status is HTTPStatus.PRECONDITION_FAILED

    @property
    def isRequestEntityTooLarge(self) -> bool:
        return self.status is HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    @property
    def isRequestUriTooLong(self) -> bool:
        return self.status is HTTPStatus.REQUEST_URI_TOO_LONG

    @property
    def isUnsupportedMediaType(self) -> bool:
        return self.status is HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    @property
    def isRequestedRangeNotSatisfiable(self) -> bool:
        return self.status is HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE

    @property
    def isExpectationFailed(self) -> bool:
        return self.status is HTTPStatus.EXPECTATION_FAILED

    @property
    def isImATeapot(self) -> bool:
        return self.status is HTTPStatus.IM_A_TEAPOT

    @property
    def isMisdirectedRequest(self) -> bool:
        return self.status is HTTPStatus.MISDIRECTED_REQUEST

    @property
    def isUnprocessableEntity(self) -> bool:
        return self.status is HTTPStatus.UNPROCESSABLE_ENTITY

    @property
    def isLocked(self) -> bool:
        return self.status is HTTPStatus.LOCKED

    @property
    def isFailedDependency(self) -> bool:
        return self.status is HTTPStatus.FAILED_DEPENDENCY

    @property
    def isTooEarly(self) -> bool:
        return self.status is HTTPStatus.TOO_EARLY

    @property
    def isUpgradeRequired(self) -> bool:
        return self.status is HTTPStatus.UPGRADE_REQUIRED

    @property
    def isPreconditionRequired(self) -> bool:
        return self.status is HTTPStatus.PRECONDITION_REQUIRED

    @property
    def isTooManyRequests(self) -> bool:
        return self.status is HTTPStatus.TOO_MANY_REQUESTS

    @property
    def isRequestHeaderFieldsTooLarge(self) -> bool:
        return self.status is HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE

    @property
    def isUnavailableForLegalReasons(self) -> bool:
        return self.status is HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS

    @property
    def isInternalServerError(self) -> bool:
        return self.status is HTTPStatus.INTERNAL_SERVER_ERROR

    @property
    def isNotImplemented(self) -> bool:
        return self.status is HTTPStatus.NOT_IMPLEMENTED

    @property
    def isBadGateway(self) -> bool:
        return self.status is HTTPStatus.BAD_GATEWAY

    @property
    def isServiceUnavailable(self) -> bool:
        return self.status is HTTPStatus.SERVICE_UNAVAILABLE

    @property
    def isGatewayTimeout(self) -> bool:
        return self.status is HTTPStatus.GATEWAY_TIMEOUT

    @property
    def isHttpVersionNotSupported(self) -> bool:
        return self.status is HTTPStatus.HTTP_VERSION_NOT_SUPPORTED

    @property
    def isVariantAlsoNegotiates(self) -> bool:
        return self.status is HTTPStatus.VARIANT_ALSO_NEGOTIATES

    @property
    def isInsufficientStorage(self) -> bool:
        return self.status is HTTPStatus.INSUFFICIENT_STORAGE

    @property
    def isLoopDetected(self) -> bool:
        return self.status is HTTPStatus.LOOP_DETECTED

    @property
    def isNotExtended(self) -> bool:
        return self.status is HTTPStatus.NOT_EXTENDED

    @property
    def isNetworkAuthenticationRequired(self) -> bool:
        return self.status is HTTPStatus.NETWORK_AUTHENTICATION_REQUIRED


class InformationalError(HTTPError):
    Continue: ClassVar[type[InformationalError]]
    SwitchingProtocols: ClassVar[type[InformationalError]]
    Processing: ClassVar[type[InformationalError]]
    EarlyHints: ClassVar[type[InformationalError]]


class Continue(InformationalError):
    status: ClassVar[HTTPStatus] = HTTPStatus.CONTINUE


class SwitchingProtocols(InformationalError):
    status: ClassVar[HTTPStatus] = HTTPStatus.SWITCHING_PROTOCOLS


class Processing(InformationalError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PROCESSING


class EarlyHints(InformationalError):
    status: ClassVar[HTTPStatus] = HTTPStatus.EARLY_HINTS


class SuccessfulError(HTTPError):
    Ok: ClassVar[type[SuccessfulError]]
    Created: ClassVar[type[SuccessfulError]]
    Accepted: ClassVar[type[SuccessfulError]]
    NonAuthoritativeInformation: ClassVar[type[SuccessfulError]]
    NoContent: ClassVar[type[SuccessfulError]]
    ResetContent: ClassVar[type[SuccessfulError]]
    PartialContent: ClassVar[type[SuccessfulError]]
    MultiStatus: ClassVar[type[SuccessfulError]]
    AlreadyReported: ClassVar[type[SuccessfulError]]
    ImUsed: ClassVar[type[SuccessfulError]]


class Ok(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.OK


class Created(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.CREATED


class Accepted(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.ACCEPTED


class NonAuthoritativeInformation(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NON_AUTHORITATIVE_INFORMATION


class NoContent(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NO_CONTENT


class ResetContent(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.RESET_CONTENT


class PartialContent(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PARTIAL_CONTENT


class MultiStatus(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.MULTI_STATUS


class AlreadyReported(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.ALREADY_REPORTED


class ImUsed(SuccessfulError):
    status: ClassVar[HTTPStatus] = HTTPStatus.IM_USED


class RedirectionError(HTTPError):
    MultipleChoices: ClassVar[type[RedirectionError]]
    MovedPermanently: ClassVar[type[RedirectionError]]
    Found: ClassVar[type[RedirectionError]]
    SeeOther: ClassVar[type[RedirectionError]]
    NotModified: ClassVar[type[RedirectionError]]
    UseProxy: ClassVar[type[RedirectionError]]
    TemporaryRedirect: ClassVar[type[RedirectionError]]
    PermanentRedirect: ClassVar[type[RedirectionError]]


class MultipleChoices(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.MULTIPLE_CHOICES


class MovedPermanently(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.MOVED_PERMANENTLY


class Found(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.FOUND


class SeeOther(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.SEE_OTHER


class NotModified(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NOT_MODIFIED


class UseProxy(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.USE_PROXY


class TemporaryRedirect(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.TEMPORARY_REDIRECT


class PermanentRedirect(RedirectionError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PERMANENT_REDIRECT


class ClientError(HTTPError):
    BadRequest: ClassVar[type[ClientError]]
    Unauthorized: ClassVar[type[ClientError]]
    PaymentRequired: ClassVar[type[ClientError]]
    Forbidden: ClassVar[type[ClientError]]
    NotFound: ClassVar[type[ClientError]]
    MethodNotAllowed: ClassVar[type[ClientError]]
    NotAcceptable: ClassVar[type[ClientError]]
    ProxyAuthenticationRequired: ClassVar[type[ClientError]]
    RequestTimeout: ClassVar[type[ClientError]]
    Conflict: ClassVar[type[ClientError]]
    Gone: ClassVar[type[ClientError]]
    LengthRequired: ClassVar[type[ClientError]]
    PreconditionFailed: ClassVar[type[ClientError]]
    RequestEntityTooLarge: ClassVar[type[ClientError]]
    RequestUriTooLong: ClassVar[type[ClientError]]
    UnsupportedMediaType: ClassVar[type[ClientError]]
    RequestedRangeNotSatisfiable: ClassVar[type[ClientError]]
    ExpectationFailed: ClassVar[type[ClientError]]
    ImATeapot: ClassVar[type[ClientError]]
    MisdirectedRequest: ClassVar[type[ClientError]]
    UnprocessableEntity: ClassVar[type[ClientError]]
    Locked: ClassVar[type[ClientError]]
    FailedDependency: ClassVar[type[ClientError]]
    TooEarly: ClassVar[type[ClientError]]
    UpgradeRequired: ClassVar[type[ClientError]]
    PreconditionRequired: ClassVar[type[ClientError]]
    TooManyRequests: ClassVar[type[ClientError]]
    RequestHeaderFieldsTooLarge: ClassVar[type[ClientError]]
    UnavailableForLegalReasons: ClassVar[type[ClientError]]


class BadRequest(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.BAD_REQUEST


class Unauthorized(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.UNAUTHORIZED


class PaymentRequired(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PAYMENT_REQUIRED


class Forbidden(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.FORBIDDEN


class NotFound(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NOT_FOUND


class MethodNotAllowed(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.METHOD_NOT_ALLOWED


class NotAcceptable(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NOT_ACCEPTABLE


class ProxyAuthenticationRequired(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PROXY_AUTHENTICATION_REQUIRED


class RequestTimeout(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.REQUEST_TIMEOUT


class Conflict(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.CONFLICT


class Gone(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.GONE


class LengthRequired(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.LENGTH_REQUIRED


class PreconditionFailed(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PRECONDITION_FAILED


class RequestEntityTooLarge(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class RequestUriTooLong(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.REQUEST_URI_TOO_LONG


class UnsupportedMediaType(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


class RequestedRangeNotSatisfiable(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE


class ExpectationFailed(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.EXPECTATION_FAILED


class ImATeapot(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.IM_A_TEAPOT


class MisdirectedRequest(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.MISDIRECTED_REQUEST


class UnprocessableEntity(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.UNPROCESSABLE_ENTITY


class Locked(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.LOCKED


class FailedDependency(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.FAILED_DEPENDENCY


class TooEarly(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.TOO_EARLY


class UpgradeRequired(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.UPGRADE_REQUIRED


class PreconditionRequired(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.PRECONDITION_REQUIRED


class TooManyRequests(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.TOO_MANY_REQUESTS


class RequestHeaderFieldsTooLarge(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE


class UnavailableForLegalReasons(ClientError):
    status: ClassVar[HTTPStatus] = HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS


class ServerError(HTTPError):
    InternalServerError: ClassVar[type[ServerError]]
    NotImplemented: ClassVar[type[ServerError]]
    BadGateway: ClassVar[type[ServerError]]
    ServiceUnavailable: ClassVar[type[ServerError]]
    GatewayTimeout: ClassVar[type[ServerError]]
    HttpVersionNotSupported: ClassVar[type[ServerError]]
    VariantAlsoNegotiates: ClassVar[type[ServerError]]
    InsufficientStorage: ClassVar[type[ServerError]]
    LoopDetected: ClassVar[type[ServerError]]
    NotExtended: ClassVar[type[ServerError]]
    NetworkAuthenticationRequired: ClassVar[type[ServerError]]


class InternalServerError(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR


class NotImplemented(
    ServerError,
):  # name from HTTPStatus.NOT_IMPLEMENTED
    status: ClassVar[HTTPStatus] = HTTPStatus.NOT_IMPLEMENTED


class BadGateway(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.BAD_GATEWAY


class ServiceUnavailable(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.SERVICE_UNAVAILABLE


class GatewayTimeout(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.GATEWAY_TIMEOUT


class HttpVersionNotSupported(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.HTTP_VERSION_NOT_SUPPORTED


class VariantAlsoNegotiates(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.VARIANT_ALSO_NEGOTIATES


class InsufficientStorage(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.INSUFFICIENT_STORAGE


class LoopDetected(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.LOOP_DETECTED


class NotExtended(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NOT_EXTENDED


class NetworkAuthenticationRequired(ServerError):
    status: ClassVar[HTTPStatus] = HTTPStatus.NETWORK_AUTHENTICATION_REQUIRED


# --- leaf bindings (declared as ClassVars on the family parents) -------------

HTTPError.Informational = InformationalError
HTTPError.Successful = SuccessfulError
HTTPError.Redirection = RedirectionError
HTTPError.Client = ClientError
HTTPError.Server = ServerError
InformationalError.Continue = Continue
InformationalError.SwitchingProtocols = SwitchingProtocols
InformationalError.Processing = Processing
InformationalError.EarlyHints = EarlyHints
SuccessfulError.Ok = Ok
SuccessfulError.Created = Created
SuccessfulError.Accepted = Accepted
SuccessfulError.NonAuthoritativeInformation = NonAuthoritativeInformation
SuccessfulError.NoContent = NoContent
SuccessfulError.ResetContent = ResetContent
SuccessfulError.PartialContent = PartialContent
SuccessfulError.MultiStatus = MultiStatus
SuccessfulError.AlreadyReported = AlreadyReported
SuccessfulError.ImUsed = ImUsed
RedirectionError.MultipleChoices = MultipleChoices
RedirectionError.MovedPermanently = MovedPermanently
RedirectionError.Found = Found
RedirectionError.SeeOther = SeeOther
RedirectionError.NotModified = NotModified
RedirectionError.UseProxy = UseProxy
RedirectionError.TemporaryRedirect = TemporaryRedirect
RedirectionError.PermanentRedirect = PermanentRedirect
ClientError.BadRequest = BadRequest
ClientError.Unauthorized = Unauthorized
ClientError.PaymentRequired = PaymentRequired
ClientError.Forbidden = Forbidden
ClientError.NotFound = NotFound
ClientError.MethodNotAllowed = MethodNotAllowed
ClientError.NotAcceptable = NotAcceptable
ClientError.ProxyAuthenticationRequired = ProxyAuthenticationRequired
ClientError.RequestTimeout = RequestTimeout
ClientError.Conflict = Conflict
ClientError.Gone = Gone
ClientError.LengthRequired = LengthRequired
ClientError.PreconditionFailed = PreconditionFailed
ClientError.RequestEntityTooLarge = RequestEntityTooLarge
ClientError.RequestUriTooLong = RequestUriTooLong
ClientError.UnsupportedMediaType = UnsupportedMediaType
ClientError.RequestedRangeNotSatisfiable = RequestedRangeNotSatisfiable
ClientError.ExpectationFailed = ExpectationFailed
ClientError.ImATeapot = ImATeapot
ClientError.MisdirectedRequest = MisdirectedRequest
ClientError.UnprocessableEntity = UnprocessableEntity
ClientError.Locked = Locked
ClientError.FailedDependency = FailedDependency
ClientError.TooEarly = TooEarly
ClientError.UpgradeRequired = UpgradeRequired
ClientError.PreconditionRequired = PreconditionRequired
ClientError.TooManyRequests = TooManyRequests
ClientError.RequestHeaderFieldsTooLarge = RequestHeaderFieldsTooLarge
ClientError.UnavailableForLegalReasons = UnavailableForLegalReasons
ServerError.InternalServerError = InternalServerError
ServerError.NotImplemented = NotImplemented
ServerError.BadGateway = BadGateway
ServerError.ServiceUnavailable = ServiceUnavailable
ServerError.GatewayTimeout = GatewayTimeout
ServerError.HttpVersionNotSupported = HttpVersionNotSupported
ServerError.VariantAlsoNegotiates = VariantAlsoNegotiates
ServerError.InsufficientStorage = InsufficientStorage
ServerError.LoopDetected = LoopDetected
ServerError.NotExtended = NotExtended
ServerError.NetworkAuthenticationRequired = NetworkAuthenticationRequired


REGISTRY: dict[HTTPStatus, type[HTTPError]] = {
    HTTPStatus.CONTINUE: Continue,
    HTTPStatus.SWITCHING_PROTOCOLS: SwitchingProtocols,
    HTTPStatus.PROCESSING: Processing,
    HTTPStatus.EARLY_HINTS: EarlyHints,
    HTTPStatus.OK: Ok,
    HTTPStatus.CREATED: Created,
    HTTPStatus.ACCEPTED: Accepted,
    HTTPStatus.NON_AUTHORITATIVE_INFORMATION: NonAuthoritativeInformation,
    HTTPStatus.NO_CONTENT: NoContent,
    HTTPStatus.RESET_CONTENT: ResetContent,
    HTTPStatus.PARTIAL_CONTENT: PartialContent,
    HTTPStatus.MULTI_STATUS: MultiStatus,
    HTTPStatus.ALREADY_REPORTED: AlreadyReported,
    HTTPStatus.IM_USED: ImUsed,
    HTTPStatus.MULTIPLE_CHOICES: MultipleChoices,
    HTTPStatus.MOVED_PERMANENTLY: MovedPermanently,
    HTTPStatus.FOUND: Found,
    HTTPStatus.SEE_OTHER: SeeOther,
    HTTPStatus.NOT_MODIFIED: NotModified,
    HTTPStatus.USE_PROXY: UseProxy,
    HTTPStatus.TEMPORARY_REDIRECT: TemporaryRedirect,
    HTTPStatus.PERMANENT_REDIRECT: PermanentRedirect,
    HTTPStatus.BAD_REQUEST: BadRequest,
    HTTPStatus.UNAUTHORIZED: Unauthorized,
    HTTPStatus.PAYMENT_REQUIRED: PaymentRequired,
    HTTPStatus.FORBIDDEN: Forbidden,
    HTTPStatus.NOT_FOUND: NotFound,
    HTTPStatus.METHOD_NOT_ALLOWED: MethodNotAllowed,
    HTTPStatus.NOT_ACCEPTABLE: NotAcceptable,
    HTTPStatus.PROXY_AUTHENTICATION_REQUIRED: ProxyAuthenticationRequired,
    HTTPStatus.REQUEST_TIMEOUT: RequestTimeout,
    HTTPStatus.CONFLICT: Conflict,
    HTTPStatus.GONE: Gone,
    HTTPStatus.LENGTH_REQUIRED: LengthRequired,
    HTTPStatus.PRECONDITION_FAILED: PreconditionFailed,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: RequestEntityTooLarge,
    HTTPStatus.REQUEST_URI_TOO_LONG: RequestUriTooLong,
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: UnsupportedMediaType,
    HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE: RequestedRangeNotSatisfiable,
    HTTPStatus.EXPECTATION_FAILED: ExpectationFailed,
    HTTPStatus.IM_A_TEAPOT: ImATeapot,
    HTTPStatus.MISDIRECTED_REQUEST: MisdirectedRequest,
    HTTPStatus.UNPROCESSABLE_ENTITY: UnprocessableEntity,
    HTTPStatus.LOCKED: Locked,
    HTTPStatus.FAILED_DEPENDENCY: FailedDependency,
    HTTPStatus.TOO_EARLY: TooEarly,
    HTTPStatus.UPGRADE_REQUIRED: UpgradeRequired,
    HTTPStatus.PRECONDITION_REQUIRED: PreconditionRequired,
    HTTPStatus.TOO_MANY_REQUESTS: TooManyRequests,
    HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE: RequestHeaderFieldsTooLarge,
    HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS: UnavailableForLegalReasons,
    HTTPStatus.INTERNAL_SERVER_ERROR: InternalServerError,
    HTTPStatus.NOT_IMPLEMENTED: NotImplemented,
    HTTPStatus.BAD_GATEWAY: BadGateway,
    HTTPStatus.SERVICE_UNAVAILABLE: ServiceUnavailable,
    HTTPStatus.GATEWAY_TIMEOUT: GatewayTimeout,
    HTTPStatus.HTTP_VERSION_NOT_SUPPORTED: HttpVersionNotSupported,
    HTTPStatus.VARIANT_ALSO_NEGOTIATES: VariantAlsoNegotiates,
    HTTPStatus.INSUFFICIENT_STORAGE: InsufficientStorage,
    HTTPStatus.LOOP_DETECTED: LoopDetected,
    HTTPStatus.NOT_EXTENDED: NotExtended,
    HTTPStatus.NETWORK_AUTHENTICATION_REQUIRED: NetworkAuthenticationRequired,
}

# flat leaf aliases on the base (HTTPError.NotFound and friends)
HTTPError.Continue = Continue
HTTPError.SwitchingProtocols = SwitchingProtocols
HTTPError.Processing = Processing
HTTPError.EarlyHints = EarlyHints
HTTPError.Ok = Ok
HTTPError.Created = Created
HTTPError.Accepted = Accepted
HTTPError.NonAuthoritativeInformation = NonAuthoritativeInformation
HTTPError.NoContent = NoContent
HTTPError.ResetContent = ResetContent
HTTPError.PartialContent = PartialContent
HTTPError.MultiStatus = MultiStatus
HTTPError.AlreadyReported = AlreadyReported
HTTPError.ImUsed = ImUsed
HTTPError.MultipleChoices = MultipleChoices
HTTPError.MovedPermanently = MovedPermanently
HTTPError.Found = Found
HTTPError.SeeOther = SeeOther
HTTPError.NotModified = NotModified
HTTPError.UseProxy = UseProxy
HTTPError.TemporaryRedirect = TemporaryRedirect
HTTPError.PermanentRedirect = PermanentRedirect
HTTPError.BadRequest = BadRequest
HTTPError.Unauthorized = Unauthorized
HTTPError.PaymentRequired = PaymentRequired
HTTPError.Forbidden = Forbidden
HTTPError.NotFound = NotFound
HTTPError.MethodNotAllowed = MethodNotAllowed
HTTPError.NotAcceptable = NotAcceptable
HTTPError.ProxyAuthenticationRequired = ProxyAuthenticationRequired
HTTPError.RequestTimeout = RequestTimeout
HTTPError.Conflict = Conflict
HTTPError.Gone = Gone
HTTPError.LengthRequired = LengthRequired
HTTPError.PreconditionFailed = PreconditionFailed
HTTPError.RequestEntityTooLarge = RequestEntityTooLarge
HTTPError.RequestUriTooLong = RequestUriTooLong
HTTPError.UnsupportedMediaType = UnsupportedMediaType
HTTPError.RequestedRangeNotSatisfiable = RequestedRangeNotSatisfiable
HTTPError.ExpectationFailed = ExpectationFailed
HTTPError.ImATeapot = ImATeapot
HTTPError.MisdirectedRequest = MisdirectedRequest
HTTPError.UnprocessableEntity = UnprocessableEntity
HTTPError.Locked = Locked
HTTPError.FailedDependency = FailedDependency
HTTPError.TooEarly = TooEarly
HTTPError.UpgradeRequired = UpgradeRequired
HTTPError.PreconditionRequired = PreconditionRequired
HTTPError.TooManyRequests = TooManyRequests
HTTPError.RequestHeaderFieldsTooLarge = RequestHeaderFieldsTooLarge
HTTPError.UnavailableForLegalReasons = UnavailableForLegalReasons
HTTPError.InternalServerError = InternalServerError
HTTPError.NotImplemented = NotImplemented
HTTPError.BadGateway = BadGateway
HTTPError.ServiceUnavailable = ServiceUnavailable
HTTPError.GatewayTimeout = GatewayTimeout
HTTPError.HttpVersionNotSupported = HttpVersionNotSupported
HTTPError.VariantAlsoNegotiates = VariantAlsoNegotiates
HTTPError.InsufficientStorage = InsufficientStorage
HTTPError.LoopDetected = LoopDetected
HTTPError.NotExtended = NotExtended
HTTPError.NetworkAuthenticationRequired = NetworkAuthenticationRequired
