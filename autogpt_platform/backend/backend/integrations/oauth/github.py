import time
from typing import Optional
from urllib.parse import urlencode

from backend.data.model import OAuth2Credentials
from backend.integrations.providers import ProviderName
from backend.util.request import Requests

from .base import BaseOAuthHandler


# --8<-- [start:GithubOAuthHandlerExample]
class GitHubOAuthHandler(BaseOAuthHandler):
    """
    Based on the documentation at:
    - [Authorizing OAuth apps - GitHub Docs](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
    - [Refreshing user access tokens - GitHub Docs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens)

    Notes:
    - By default, token expiration is disabled on GitHub Apps. This means the access
      token doesn't expire and no refresh token is returned by the authorization flow.
    - When token expiration gets enabled, any existing tokens will remain non-expiring.
    - When token expiration gets disabled, token refreshes will return a non-expiring
      access token *with no refresh token*.
    """  # noqa

    PROVIDER_NAME = ProviderName.GITHUB

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_base_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.revoke_url = "https://api.github.com/applications/{client_id}/token"

    def get_login_url(
        self, scopes: list[str], state: str, code_challenge: Optional[str]
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self.auth_base_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, scopes: list[str], code_verifier: Optional[str]
    ) -> OAuth2Credentials:
        return await self._request_tokens(
            {"code": code, "redirect_uri": self.redirect_uri}
        )

    async def revoke_tokens(self, credentials: OAuth2Credentials) -> bool:
        if not credentials.access_token:
            raise ValueError("No access token to revoke")

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        await Requests().delete(
            url=self.revoke_url.format(client_id=self.client_id),
            auth=(self.client_id, self.client_secret),
            headers=headers,
            json={"access_token": credentials.access_token.get_secret_value()},
        )
        return True

    async def _refresh_tokens(
        self, credentials: OAuth2Credentials
    ) -> OAuth2Credentials:
        if not credentials.refresh_token:
            return credentials

        return await self._request_tokens(
            {
                "refresh_token": credentials.refresh_token.get_secret_value(),
                "grant_type": "refresh_token",
            }
        )

    async def _request_tokens(
        self,
        params: dict[str, str],
        current_credentials: Optional[OAuth2Credentials] = None,
    ) -> OAuth2Credentials:
        request_body = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            **params,
        }
        headers = {"Accept": "application/json"}
        response = await Requests().post(
            self.token_url, data=request_body, headers=headers
        )
        token_data: dict = response.json()

        username = await self._request_username(token_data["access_token"])

        now = int(time.time())
        new_credentials = OAuth2Credentials(
            provider=self.PROVIDER_NAME,
            title=current_credentials.title if current_credentials else None,
            username=username,
            access_token=token_data["access_token"],
            # Token refresh responses have an empty `scope` property (see docs),
            # so we have to get the scope from the existing credentials object.
            scopes=(
                token_data.get("scope", "").split(",")
                or (current_credentials.scopes if current_credentials else [])
            ),
            # Refresh token and expiration intervals are only given if token expiration
            # is enabled in the GitHub App's settings.
            refresh_token=token_data.get("refresh_token"),
            access_token_expires_at=(
                now + expires_in
                if (expires_in := token_data.get("expires_in", None))
                else None
            ),
            refresh_token_expires_at=(
                now + expires_in
                if (expires_in := token_data.get("refresh_token_expires_in", None))
                else None
            ),
        )
        if current_credentials:
            new_credentials.id = current_credentials.id
        return new_credentials

    async def _request_username(self, access_token: str) -> str | None:
        url = "https://api.github.com/user"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = await Requests().get(url, headers=headers)

        if not response.ok:
            return None

        # Get the login (username)
        resp = response.json()
        return resp.get("login")


# --8<-- [end:GithubOAuthHandlerExample]
