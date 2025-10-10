from .config import THUMB_BOX_SIZE, MIN_CELL_SPACING, MAX_CELL_SPACING

def calculate_dynamic_grid_columns(viewport_width: int) -> tuple[int, int]:
    """
    Calculates the optimal number of columns and spacing for a grid layout
    to best fit the available viewport width.
    """
    if viewport_width < THUMB_BOX_SIZE[0]:
        return 1, MIN_CELL_SPACING

    # Account for some margin on the sides
    available_width = viewport_width - 20
    cell_width = THUMB_BOX_SIZE[0]

    # Calculate how many cells can fit with minimum spacing
    num_cols = available_width // (cell_width + MIN_CELL_SPACING)
    num_cols = max(1, num_cols)

    # Distribute the remaining space evenly
    total_cell_width = num_cols * cell_width
    total_spacing = available_width - total_cell_width
    spacing = total_spacing / (num_cols + 1)

    # Clamp spacing to reasonable limits
    spacing = int(max(MIN_CELL_SPACING, min(spacing, MAX_CELL_SPACING)))

    return num_cols, spacing
