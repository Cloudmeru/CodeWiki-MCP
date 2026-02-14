"""Pydantic schemas and structured response types for CodeWiki MCP."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------
REPO_URL_PATTERN = re.compile(
    r"^https?://(github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+(/.*)?$"
)

OWNER_REPO_PATTERN = re.compile(
    r"^[\w.\-]+/[\w.\-]+$"
)


# ---------------------------------------------------------------------------
# Input schemas (like Zod in DeepWiki MCP)
# ---------------------------------------------------------------------------
class RepoInput(BaseModel):
    """Validated repository identifier — accepts full URL or owner/repo shorthand."""

    repo_url: str = Field(
        ...,
        description=(
            "Repository URL (e.g. https://github.com/microsoft/vscode) "
            "or shorthand owner/repo (e.g. microsoft/vscode)."
        ),
    )

    @field_validator("repo_url")
    @classmethod
    def normalize_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url must not be empty")

        # Shorthand: owner/repo → full GitHub URL
        if OWNER_REPO_PATTERN.match(v):
            return f"https://github.com/{v}"

        if not REPO_URL_PATTERN.match(v):
            raise ValueError(
                f"Invalid repository URL: '{v}'. "
                "Expected https://github.com/owner/repo or owner/repo shorthand."
            )
        return v


class SearchInput(RepoInput):
    """Input for the search_code_wiki tool."""

    query: str = Field(
        ...,
        min_length=1,
        description="The question to ask about the repository.",
    )

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v


class TopicsInput(RepoInput):
    """Input for the list_code_wiki_topics tool."""

    pass  # Only repo_url needed


class SectionInput(RepoInput):
    """Input for the read_wiki_section tool."""

    section_title: str = Field(
        ...,
        min_length=1,
        description="Title (or partial title) of the section to retrieve.",
    )

    @field_validator("section_title")
    @classmethod
    def section_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("section_title must not be blank")
        return v


# ---------------------------------------------------------------------------
# Structured response types (like ErrorEnvelope in DeepWiki MCP)
# ---------------------------------------------------------------------------
class ResponseStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    PARTIAL = "partial"


class ErrorCode(str, Enum):
    VALIDATION = "VALIDATION"
    TIMEOUT = "TIMEOUT"
    DRIVER_ERROR = "DRIVER_ERROR"
    NO_CONTENT = "NO_CONTENT"
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    INTERNAL = "INTERNAL"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class ResponseMeta(BaseModel):
    """Metadata about the response — timing, size, etc."""

    elapsed_ms: int = 0
    char_count: int = 0
    attempt: int = 1
    max_attempts: int = 1
    truncated: bool = False


class ToolResponse(BaseModel):
    """Structured response from any CodeWiki tool."""

    status: ResponseStatus
    code: ErrorCode | None = None
    message: str | None = None
    data: str | None = None
    repo_url: str | None = None
    query: str | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    def to_text(self) -> str:
        """Serialize to JSON string for MCP transport."""
        return json.dumps(self.model_dump(exclude_none=True), indent=2)

    # -- Factory helpers --

    @classmethod
    def success(
        cls,
        data: str,
        *,
        repo_url: str | None = None,
        query: str | None = None,
        meta: ResponseMeta | None = None,
    ) -> ToolResponse:
        m = meta or ResponseMeta()
        m.char_count = len(data)
        return cls(
            status=ResponseStatus.OK,
            data=data,
            repo_url=repo_url,
            query=query,
            meta=m,
        )

    @classmethod
    def error(
        cls,
        code: ErrorCode,
        message: str,
        *,
        repo_url: str | None = None,
        query: str | None = None,
        meta: ResponseMeta | None = None,
    ) -> ToolResponse:
        return cls(
            status=ResponseStatus.ERROR,
            code=code,
            message=message,
            repo_url=repo_url,
            query=query,
            meta=meta or ResponseMeta(),
        )


def validate_search_input(repo_url: str, query: str) -> SearchInput | ToolResponse:
    """Validate and normalize search inputs. Returns SearchInput or ToolResponse error."""
    try:
        return SearchInput(repo_url=repo_url, query=query)
    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
            query=query,
        )


def validate_topics_input(repo_url: str) -> TopicsInput | ToolResponse:
    """Validate and normalize topics inputs. Returns TopicsInput or ToolResponse error."""
    try:
        return TopicsInput(repo_url=repo_url)
    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
        )


def validate_section_input(repo_url: str, section_title: str) -> SectionInput | ToolResponse:
    """Validate and normalize section inputs. Returns SectionInput or ToolResponse error."""
    try:
        return SectionInput(repo_url=repo_url, section_title=section_title)
    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
        )
