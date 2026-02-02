"""Unit tests for hive utility functions."""

import json
import tempfile
from pathlib import Path
import pytest

from src.hive_utils import get_hive_config, load_hives_config
from src.id_utils import normalize_hive_name
from src.config import BeesConfig, HiveConfig, save_bees_config


class TestNormalizeHiveName:
    """Tests for normalize_hive_name function (from id_utils)."""
    
    def test_lowercase_conversion(self):
        """Test that uppercase is converted to lowercase."""
        assert normalize_hive_name("BackEnd") == "backend"
        assert normalize_hive_name("FRONTEND") == "frontend"
    
    def test_space_to_underscore(self):
        """Test that spaces are converted to underscores."""
        assert normalize_hive_name("Back End") == "back_end"
        assert normalize_hive_name("My Hive Name") == "my_hive_name"
    
    def test_hyphen_to_underscore(self):
        """Test that hyphens are converted to underscores."""
        assert normalize_hive_name("back-end") == "back_end"
        assert normalize_hive_name("my-hive-name") == "my_hive_name"
    
    def test_already_normalized(self):
        """Test that already normalized names pass through unchanged."""
        assert normalize_hive_name("backend") == "backend"
        assert normalize_hive_name("my_hive") == "my_hive"


class TestGetHiveConfig:
    """Tests for get_hive_config function."""
    
    def test_get_hive_config_existing_hive(self, tmp_path, monkeypatch):
        """Test getting config for an existing hive."""
        # Set up temp directory as cwd
        monkeypatch.chdir(tmp_path)
        
        # Create .bees directory
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        # Create config.json with hive
        config_data = {
            "hives": {
                "backend": {
                    "path": str(tmp_path / "backend"),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T10:00:00"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        
        config_path = bees_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        # Test getting hive config by normalized name
        result = get_hive_config("backend")
        assert result is not None
        assert result["path"] == str(tmp_path / "backend")
        assert result["display_name"] == "Backend"
        assert result["created_at"] == "2026-02-01T10:00:00"
        
        # Test getting hive config by display name (should normalize)
        result = get_hive_config("Backend")
        assert result is not None
        assert result["path"] == str(tmp_path / "backend")
    
    def test_get_hive_config_nonexistent_hive(self, tmp_path, monkeypatch):
        """Test getting config for a non-existent hive returns None."""
        monkeypatch.chdir(tmp_path)
        
        # Create .bees directory with empty config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        config_data = {
            "hives": {},
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        
        config_path = bees_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        # Test getting non-existent hive
        result = get_hive_config("nonexistent")
        assert result is None
    
    def test_get_hive_config_no_config_file(self, tmp_path, monkeypatch):
        """Test getting config when config.json doesn't exist returns None."""
        monkeypatch.chdir(tmp_path)
        
        result = get_hive_config("backend")
        assert result is None


class TestLoadHivesConfig:
    """Tests for load_hives_config function."""
    
    def test_load_hives_config_existing(self, tmp_path, monkeypatch):
        """Test loading existing config."""
        monkeypatch.chdir(tmp_path)
        
        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tmp_path / "backend"),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=True,
            schema_version="1.0"
        )
        
        save_bees_config(config)
        
        # Load config
        loaded = load_hives_config()
        assert loaded is not None
        assert len(loaded.hives) == 1
        assert "backend" in loaded.hives
        assert loaded.allow_cross_hive_dependencies is True
    
    def test_load_hives_config_nonexistent(self, tmp_path, monkeypatch):
        """Test loading config when file doesn't exist returns None."""
        monkeypatch.chdir(tmp_path)
        
        result = load_hives_config()
        assert result is None
