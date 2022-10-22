import re
from typing import Any, Dict, Union, Coroutine

from httpx import Timeout
from postgrest import AsyncFilterRequestBuilder, AsyncPostgrestClient, AsyncRequestBuilder
from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT

from supafunc import FunctionsClient
from .lib.auth_client import SupabaseAuthClient
from .lib.client_options import ClientOptions
from .lib.storage_client import SupabaseStorageClient

from .exceptions import SupabaseException


class AsyncSupabaseClient:
    """Supabase client class."""

    def __init__(
            self,
            supabase_url: str,
            supabase_key: str,
            options: ClientOptions = ClientOptions(),
    ):
        """Instantiate the client.

        Parameters
        ----------
        supabase_url: str
            The URL to the Supabase instance that should be connected to.
        supabase_key: str
            The API key to the Supabase instance that should be connected to.
        **options
            Any extra settings to be optionally specified - also see the
            `DEFAULT_OPTIONS` dict.
        """

        if not supabase_url:
            raise SupabaseException("supabase_url is required")
        if not supabase_key:
            raise SupabaseException("supabase_key is required")

        # Check if the url and key are valid
        if not re.match(r"^(https?)://.+", supabase_url):
            raise SupabaseException("Invalid URL")

        # Check if the key is a valid JWT
        if not re.match(r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$", supabase_key):
            raise SupabaseException("Invalid API key")

        self.supabase_url = supabase_url
        self.supabase_key = supabase_key

        options.headers.update(self._get_auth_headers())

        self.rest_url: str = f"{supabase_url}/rest/v1"
        self.realtime_url: str = f"{supabase_url}/realtime/v1".replace("http", "ws")
        self.auth_url: str = f"{supabase_url}/auth/v1"
        self.storage_url = f"{supabase_url}/storage/v1"

        is_platform = re.search(r"(supabase\.co)|(supabase\.in)", supabase_url)
        if is_platform:
            url_parts = supabase_url.split(".")
            self.functions_url = (
                f"{url_parts[0]}.functions.{url_parts[1]}.{url_parts[2]}"
            )
        else:
            self.functions_url = f"{supabase_url}/functions/v1"

        self.schema: str = options.schema

        # Instantiate clients.
        self.auth = self._init_supabase_auth_client(
            auth_url=self.auth_url,
            client_options=options,
        )
        # TODO: Bring up to parity with JS client.
        # self.realtime: SupabaseRealtimeClient = self._init_realtime_client(
        #     realtime_url=self.realtime_url,
        #     supabase_key=self.supabase_key,
        # )
        self.realtime = None
        self.postgrest = self._init_postgrest_client(
            rest_url=self.rest_url,
            supabase_key=self.supabase_key,
            headers=options.headers,
            schema=options.schema,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.postgrest.session.aclose()

    def functions(self) -> FunctionsClient:
        """Create instance of the functions client"""
        return FunctionsClient(self.functions_url, self._get_auth_headers())

    def storage(self) -> SupabaseStorageClient:
        """Create instance of the storage client"""
        return SupabaseStorageClient(self.storage_url, self._get_auth_headers())

    def table(self, table_name: str) -> AsyncRequestBuilder:
        """Perform a table operation.

        Note that the supabase client uses the `from` method, but in Python,
        this is a reserved keyword, so we have elected to use the name `table`.
        Alternatively you can use the `.on()` method.
        """
        return self.on(table_name)

    def on(self, table_name: str) -> AsyncRequestBuilder:
        """
        An alias for `from_`.
        """
        return self.postgrest.from_(table_name)

    def from_(self, table_name: str) -> AsyncRequestBuilder:
        """Perform a table operation.

        See the `table` method.
        """
        return self.postgrest.from_(table_name)

    def rpc(self, fn: str, params: Dict[Any, Any]) -> Coroutine[Any, Any, AsyncFilterRequestBuilder]:
        """Performs a stored procedure call.

        Parameters
        ----------
        fn : callable
            The stored procedure call to be executed.
        params : dict of any
            Parameters passed into the stored procedure call.

        Returns
        -------
        SyncFilterRequestBuilder
            Returns a filter builder. This lets you apply filters on the response
            of an RPC.
        """
        return self.postgrest.rpc(fn, params)

    @staticmethod
    def _init_supabase_auth_client(
            auth_url: str,
            client_options: ClientOptions,
    ) -> SupabaseAuthClient:
        """Creates a wrapped instance of the GoTrue SupabaseClient."""
        return SupabaseAuthClient(
            url=auth_url,
            auto_refresh_token=client_options.auto_refresh_token,
            persist_session=client_options.persist_session,
            local_storage=client_options.local_storage,
            headers=client_options.headers,
        )

    @staticmethod
    def _init_postgrest_client(
            rest_url: str,
            supabase_key: str,
            headers: Dict[str, str],
            schema: str,
            timeout: Union[int, float, Timeout] = DEFAULT_POSTGREST_CLIENT_TIMEOUT,
    ) -> AsyncPostgrestClient:
        """Private helper for creating an instance of the Postgrest client."""
        client = AsyncPostgrestClient(
            rest_url, headers=headers, schema=schema, timeout=timeout
        )
        client.auth(token=supabase_key)
        return client

    def _get_auth_headers(self) -> Dict[str, str]:
        """Helper method to get auth headers."""
        # What's the corresponding method to get the token
        return {
            "apiKey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }