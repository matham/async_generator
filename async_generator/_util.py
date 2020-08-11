import sys
from functools import wraps
from ._impl import isasyncgenfunction


class aclosing:
    def __init__(self, aiter):
        self._aiter = aiter

    async def __aenter__(self):
        return self._aiter

    async def __aexit__(self, *args):
        await self._aiter.aclose()


# Very much derived from the one in contextlib, by copy/pasting and then
# asyncifying everything. (Also I dropped the obscure support for using
# context managers as function decorators. It could be re-added; I just
# couldn't be bothered.)
# So this is a derivative work licensed under the PSF License, which requires
# the following notice:
#
# Copyright © 2001-2017 Python Software Foundation; All Rights Reserved
class _AsyncGeneratorContextManager:
    def __init__(self, func, args, kwds):
        self._func_name = func.__name__
        self._agen = func(*args, **kwds).__aiter__()

    async def __aenter__(self):
        if sys.version_info < (3, 5, 2):
            self._agen = await self._agen
        try:
            return await self._agen.asend(None)
        except StopAsyncIteration:
            raise RuntimeError("async generator didn't yield") from None

    async def __aexit__(self, type, value, traceback):
        async with aclosing(self._agen):
            if type is None:
                try:
                    await self._agen.asend(None)
                except StopAsyncIteration:
                    return False
                else:
                    raise RuntimeError("async generator didn't stop")
            else:
                # It used to be possible to have type != None, value == None:
                #    https://bugs.python.org/issue1705170
                # but AFAICT this can't happen anymore.
                assert value is not None
                try:
                    await self._agen.athrow(type, value, traceback)
                    if sys.version_info[:2] >= (3, 8) or not isinstance(value, GeneratorExit):
                        raise RuntimeError(
                            "async generator didn't stop after athrow()"
                        )
                except StopAsyncIteration as exc:
                    # Suppress StopIteration *unless* it's the same exception
                    # that was passed to throw(). This prevents a
                    # StopIteration raised inside the "with" statement from
                    # being suppressed.
                    return (exc is not value)
                except RuntimeError as exc:
                    # Don't re-raise the passed in exception. (issue27112)
                    if exc is value:
                        return False
                    # Likewise, avoid suppressing if a StopIteration exception
                    # was passed to throw() and later wrapped into a
                    # RuntimeError (see PEP 479).
                    if (isinstance(value, (StopIteration, StopAsyncIteration))
                            and exc.__cause__ is value):
                        return False
                    raise
                except:
                    # only re-raise if it's *not* the exception that was
                    # passed to throw(), because __exit__() must not raise an
                    # exception unless __exit__() itself failed. But throw()
                    # has to raise the exception to signal propagation, so
                    # this fixes the impedance mismatch between the throw()
                    # protocol and the __exit__() protocol.
                    #
                    if sys.exc_info()[1] is value:
                        return False
                    raise

    def __enter__(self):
        raise RuntimeError(
            "use 'async with {func_name}(...)', not 'with {func_name}(...)'".
            format(func_name=self._func_name)
        )

    def __exit__(self):  # pragma: no cover
        assert False, """Never called, but should be defined"""


def asynccontextmanager(func):
    """Like @contextmanager, but async."""
    if not isasyncgenfunction(func):
        raise TypeError(
            "must be an async generator (native or from async_generator; "
            "if using @async_generator then @acontextmanager must be on top."
        )

    @wraps(func)
    def helper(*args, **kwds):
        return _AsyncGeneratorContextManager(func, args, kwds)

    # A hint for sphinxcontrib-trio:
    helper.__returns_acontextmanager__ = True
    return helper
