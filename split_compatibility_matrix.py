#!/usr/bin/env python3
"""Split large compatibility matrix into smaller chunks."""

import json
import os
from pathlib import Path
from typing import Dict, Any
import math


def split_compatibility_matrix(
    input_file: str = "data/compatibility_matrix.json",
    output_dir: str = "data/compatibility",
    chunk_size: int = 100
) -> None:
    """
    Split compatibility matrix into smaller files.

    Args:
        input_file: Path to the large compatibility matrix
        output_dir: Directory to store split files
        chunk_size: Number of licenses per chunk
    """
    # Load the full matrix
    print(f"Loading compatibility matrix from {input_file}...")
    with open(input_file, 'r') as f:
        data = json.load(f)

    # Extract metadata and matrix
    metadata = {
        "version": data.get("version", "1.0"),
        "generated": data.get("generated"),
        "total_licenses": data.get("total_licenses", 0)
    }

    compatibility = data.get("compatibility", {})
    license_ids = sorted(list(compatibility.keys()))
    total_licenses = len(license_ids)

    print(f"Found {total_licenses} licenses in the matrix")

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Calculate number of chunks needed
    num_chunks = math.ceil(total_licenses / chunk_size)

    # Create index file
    index = {
        "version": metadata["version"],
        "generated": metadata["generated"],
        "total_licenses": total_licenses,
        "chunk_size": chunk_size,
        "num_chunks": num_chunks,
        "chunks": []
    }

    # Split the matrix into chunks
    for chunk_idx in range(num_chunks):
        start_idx = chunk_idx * chunk_size
        end_idx = min((chunk_idx + 1) * chunk_size, total_licenses)
        chunk_licenses = license_ids[start_idx:end_idx]

        chunk_data = {
            "chunk_id": chunk_idx,
            "start_index": start_idx,
            "end_index": end_idx,
            "licenses": chunk_licenses,
            "compatibility": {}
        }

        # Add compatibility data for licenses in this chunk
        for license_id in chunk_licenses:
            chunk_data["compatibility"][license_id] = compatibility[license_id]

        # Save chunk file
        chunk_file = f"compatibility_chunk_{chunk_idx:03d}.json"
        chunk_path = os.path.join(output_dir, chunk_file)

        with open(chunk_path, 'w') as f:
            json.dump(chunk_data, f, indent=2)

        print(f"Created chunk {chunk_idx + 1}/{num_chunks}: {chunk_file} ({len(chunk_licenses)} licenses)")

        # Add to index
        index["chunks"].append({
            "chunk_id": chunk_idx,
            "file": chunk_file,
            "start_license": chunk_licenses[0] if chunk_licenses else None,
            "end_license": chunk_licenses[-1] if chunk_licenses else None,
            "license_count": len(chunk_licenses)
        })

    # Save index file
    index_path = os.path.join(output_dir, "compatibility_index.json")
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"\nCreated index file: {index_path}")
    print(f"Total size of original file: {os.path.getsize(input_file) / (1024*1024):.2f} MB")

    # Calculate total size of chunks
    total_chunk_size = 0
    for chunk_info in index["chunks"]:
        chunk_path = os.path.join(output_dir, chunk_info["file"])
        total_chunk_size += os.path.getsize(chunk_path)

    print(f"Total size of chunks: {total_chunk_size / (1024*1024):.2f} MB")
    print(f"Average chunk size: {(total_chunk_size / num_chunks) / (1024*1024):.2f} MB")


def load_split_matrix(compatibility_dir: str = "data/compatibility") -> Dict[str, Any]:
    """
    Load split compatibility matrix back into memory.

    Args:
        compatibility_dir: Directory containing split files

    Returns:
        Full compatibility matrix dictionary
    """
    index_path = os.path.join(compatibility_dir, "compatibility_index.json")

    with open(index_path, 'r') as f:
        index = json.load(f)

    # Reconstruct full matrix
    full_matrix = {
        "version": index["version"],
        "generated": index["generated"],
        "total_licenses": index["total_licenses"],
        "compatibility": {}
    }

    # Load each chunk
    for chunk_info in index["chunks"]:
        chunk_path = os.path.join(compatibility_dir, chunk_info["file"])
        with open(chunk_path, 'r') as f:
            chunk_data = json.load(f)

        # Merge compatibility data
        full_matrix["compatibility"].update(chunk_data["compatibility"])

    return full_matrix


if __name__ == "__main__":
    # Split the matrix
    split_compatibility_matrix()

    # Verify by loading it back
    print("\nVerifying split matrix...")
    reconstructed = load_split_matrix()
    print(f"Reconstructed matrix contains {len(reconstructed['compatibility'])} licenses")