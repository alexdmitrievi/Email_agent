"""Tests for multimodal attachment processing."""

import os
import tempfile

import pytest

from app.services.multimodal_service import SUPPORTED_TYPES, analyze_attachment


def test_supported_types():
    assert ".jpg" in SUPPORTED_TYPES
    assert ".png" in SUPPORTED_TYPES
    assert ".pdf" in SUPPORTED_TYPES
    assert ".docx" not in SUPPORTED_TYPES


@pytest.mark.asyncio
async def test_analyze_nonexistent_file():
    result = await analyze_attachment("/nonexistent/file.jpg")
    assert result == ""


@pytest.mark.asyncio
async def test_analyze_unsupported_type():
    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    try:
        result = await analyze_attachment(path)
        assert "[Файл:" in result
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_analyze_pdf():
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, b"%PDF-1.4 test content")
    os.close(fd)
    try:
        result = await analyze_attachment(path)
        assert "[Документ:" in result
    finally:
        os.unlink(path)
