#!/usr/bin/env python3
"""Compatibility entry point for the installed Literature Pipeline converter."""

from literature_pipeline.pdf2md import (  # noqa: F401
    MAX_PDF_BYTES,
    ConversionError,
    ConversionOptions,
    build_parser,
    convert_pdf,
    load_env_file,
    main,
    organize_result,
    positive_int,
    validate_options,
)


if __name__ == "__main__":
    raise SystemExit(main())
