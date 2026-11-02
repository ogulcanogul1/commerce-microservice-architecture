import re
from app.rag.ingestion.models import Element, ElementType


def parse_markdown_to_elements(
    blocks: list[tuple[str, int, int]]
) -> list[Element]:
    """Converts stitched Markdown blocks into typed, structured Element objects.

    Tracks heading hierarchy to assign `heading_path` to each element.
    Recognizes HEADING, TABLE, LIST, and PARAGRAPH blocks.

    Args:
        blocks: List of (text, page_start, page_end) tuples.

    Returns:
        List of structured Element instances.
    """
    elements: list[Element] = []
    # Heading hierarchy stack: list of (level, title) tuples
    heading_stack: list[tuple[int, str]] = []

    for text, page_start, page_end in blocks:
        lines = text.splitlines()
        idx = 0

        while idx < len(lines):
            line = lines[idx].strip()

            # Skip empty lines
            if not line:
                idx += 1
                continue

            # 1. Heading (#, ##, ###, ...)
            heading_match = re.match(r"^(#[\s#]*)\s+(.*)$", line)
            if heading_match:
                hashes_part, raw_title = heading_match.groups()
                level = hashes_part.count("#")
                title = raw_title.lstrip("#").strip()

                # Pop headings of equal or deeper level from the stack
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                # For this heading, the path is the stack after popping
                heading_parent_path = [t for _, t in heading_stack]

                elements.append(
                    Element(
                        type=ElementType.HEADING,
                        text=title,
                        page_start=page_start,
                        page_end=page_end,
                        heading_path=heading_parent_path,
                    )
                )
                heading_stack.append((level, title))
                idx += 1
                continue

            # For non-heading elements, their path is the full active heading stack
            current_path = [t for _, t in heading_stack]

            # 2. Table (| Col 1 | Col 2 |)
            if line.startswith("|"):
                table_lines = []
                while idx < len(lines) and lines[idx].strip().startswith("|"):
                    table_lines.append(lines[idx].strip())
                    idx += 1

                elements.append(
                    Element(
                        type=ElementType.TABLE,
                        text="\n".join(table_lines),
                        page_start=page_start,
                        page_end=page_end,
                        heading_path=list(current_path),
                    )
                )
                continue

            # 3. List Item (- item, * item, 1. item)
            list_match = re.match(r"^(\*|-|\d+\.)\s+", line)
            if list_match:
                list_lines = []
                while idx < len(lines):
                    l = lines[idx].strip()
                    if not l:
                        break
                    if re.match(r"^(\*|-|\d+\.)\s+", l) or l.startswith("  "):
                        list_lines.append(l)
                        idx += 1
                    else:
                        break

                elements.append(
                    Element(
                        type=ElementType.LIST,
                        text="\n".join(list_lines),
                        page_start=page_start,
                        page_end=page_end,
                        heading_path=list(current_path),
                    )
                )
                continue

            # 4. Regular Paragraph
            para_lines = []
            while idx < len(lines):
                l = lines[idx].strip()
                if not l:
                    break
                # If a new structure starts, end the paragraph
                if (
                    re.match(r"^#[\s#]*\s+", l)
                    or l.startswith("|")
                    or re.match(r"^(\*|-|\d+\.)\s+", l)
                ):
                    break
                para_lines.append(l)
                idx += 1

            if para_lines:
                elements.append(
                    Element(
                        type=ElementType.PARAGRAPH,
                        text=" ".join(para_lines),
                        page_start=page_start,
                        page_end=page_end,
                        heading_path=list(current_path),
                    )
                )

    return elements
