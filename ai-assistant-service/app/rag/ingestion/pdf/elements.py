import re
from app.rag.ingestion.models import Element, ElementType


def parse_markdown_to_elements(
    pages: list[tuple[int, str]]
) -> list[Element]:
    """Converts cleaned page markdown texts into typed, structured Element objects.

    Each element is initialized with page_start = page_number and page_end = page_number,
    preventing page range explosion across entire pages.
    Maintains a continuous heading hierarchy stack across pages.

    Args:
        pages: List of (page_number, cleaned_page_text) tuples.

    Returns:
        List of structured Element instances.
    """
    elements: list[Element] = []
    # Heading hierarchy stack: list of (level, title) tuples preserved across pages
    heading_stack: list[tuple[int, str]] = []

    for page_num, text in pages:
        if not text.strip():
            continue

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

                heading_parent_path = [t for _, t in heading_stack]

                elements.append(
                    Element(
                        type=ElementType.HEADING,
                        text=title,
                        page_start=page_num,
                        page_end=page_num,
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
                        page_start=page_num,
                        page_end=page_num,
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
                        page_start=page_num,
                        page_end=page_num,
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
                        page_start=page_num,
                        page_end=page_num,
                        heading_path=list(current_path),
                    )
                )

    return elements
