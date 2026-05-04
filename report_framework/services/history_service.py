from file_io import refresh_prev_files, save_with_backup


def save_source_text(project_root: str, file_path: str, source_text: str):
    return save_with_backup(project_root, file_path, source_text)


def refresh_baseline(project_root: str):
    return refresh_prev_files(project_root)
