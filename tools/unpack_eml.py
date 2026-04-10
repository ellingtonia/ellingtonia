#!/usr/bin/env python3
"""Extract text and attachments from one or more .eml files."""

import argparse
from email import policy
from email.parser import BytesParser
from pathlib import Path


def make_unique_path(dest_dir: Path, name: str) -> Path:
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        candidate = dest_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def write_payload(part, dest_dir: Path, prefix: str = "attachment") -> Path:
    filename = part.get_filename()
    if filename:
        target = dest_dir / filename
    else:
        extension = Path(part.get_content_type().split('/')[-1]).suffix
        target = dest_dir / f"{prefix}.{extension or 'bin'}"

    target = make_unique_path(dest_dir, target.name)
    with target.open("wb") as file_obj:
        file_obj.write(part.get_payload(decode=True) or b"")
    return target


def extract_message(eml_path: Path, output_dir: Path) -> None:
    with eml_path.open("rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"Output path exists and is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    header_path = output_dir / "headers.txt"
    with header_path.open("w", encoding="utf-8") as headers_file:
        for name, value in msg.items():
            headers_file.write(f"{name}: {value}\n")

    created_paths = [output_dir.resolve(), header_path.resolve()]
    body_texts = []
    attachments = []

    for part in msg.walk():
        if part.is_multipart():
            continue

        content_disposition = part.get_content_disposition()

        if content_disposition == "attachment" or part.get_filename():
            path = write_payload(part, output_dir)
            attachments.append(path)
            created_paths.append(path.resolve())
            continue

        if part.get_content_type() == "text/plain":
            body_texts.append(("text", part.get_content()))
        elif part.get_content_type() == "text/html":
            body_texts.append(("html", part.get_content()))
        elif content_disposition == "inline" and part.get_filename():
            attachments.append(write_payload(part, output_dir))

    if body_texts:
        text_path = output_dir / "body.txt"
        html_path = output_dir / "body.html"
        plain_parts = [text for kind, text in body_texts if kind == "text"]
        html_parts = [text for kind, text in body_texts if kind == "html"]

        if plain_parts:
            with text_path.open("w", encoding="utf-8") as body_file:
                body_file.write("\n\n".join(plain_parts))
        elif html_parts:
            with html_path.open("w", encoding="utf-8") as body_file:
                body_file.write("\n\n".join(html_parts))
    else:
        missing = output_dir / "body.txt"
        missing.write_text("", encoding="utf-8")
        created_paths.append(missing.resolve())

    print(f"Extracted {eml_path.name} -> {output_dir.resolve()}")
    print("Created files:")
    for path in created_paths:
        print(f"  {path}")
    if attachments:
        print(f"  attachments: {len(attachments)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "eml_files",
        nargs="+",
        help="One or more .eml files to unpack.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory in which to write extracted body text and attachments.",
    )
    args = parser.parse_args()

    base_output = Path(args.output_dir).expanduser().resolve()
    for eml_path_str in args.eml_files:
        eml_path = Path(eml_path_str).expanduser().resolve()
        if not eml_path.exists():
            print(f"Skipping missing file: {eml_path}")
            continue

        message_dir = base_output / eml_path.stem
        extract_message(eml_path, message_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
