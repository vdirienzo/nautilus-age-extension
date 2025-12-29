#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGE Encryption Extension for Nautilus
======================================
Nautilus extension for encrypting/decrypting files with age (Actually Good Encryption)

Features:
- Encrypt individual files
- Encrypt multiple files at once
- Encrypt complete folders (tar.gz + age)
- Decrypt .age files
- Secure deletion of original file (optional)
- Integrity verification before decrypting
- System notifications

Author: Homero Thompson del Lago del Terror
Date: December 2025
License: MIT
"""

import argparse
import base64
import json
import logging
import os
import pty
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Dict, List, Optional, Tuple

# Configure logging for the extension (errors only)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(name)s: %(levelname)s: %(message)s'
)
logger = logging.getLogger('age-nautilus')

# Rate limiting constants
RATE_LIMIT_MAX_ATTEMPTS = 3
RATE_LIMIT_LOCKOUT_SECONDS = 30
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes

# === PKCS#11 HSM Support (Optional) ===
# SafeNet eToken module paths to auto-detect
PKCS11_MODULE_PATHS = [
    '/usr/lib/libeToken.so',
    '/usr/lib64/libeToken.so',
    '/opt/eToken/lib/libeToken.so',
    '/usr/lib/x86_64-linux-gnu/libeToken.so',
    '/usr/lib/i386-linux-gnu/libeToken.so',
]
PKCS11_RANDOM_BYTES = 256  # 2048 bits of entropy (~342 chars Base64)
PKCS11_TIMEOUT = 30  # seconds

# Detect available Nautilus version
# IMPORTANT: DO NOT use exit() - it crashes Nautilus
from gi import require_version

NAUTILUS_VERSION = None
_import_error = None

# Try Nautilus 4.1 (Debian 13/Trixie, Ubuntu 24.04+)
try:
    require_version('Nautilus', '4.1')
    require_version('Gtk', '4.0')
    require_version('Gdk', '4.0')
    from gi.repository import Nautilus, GObject, Gtk, Gio, Gdk, GLib
    NAUTILUS_VERSION = 4
except (ValueError, ImportError):
    pass

# Try Nautilus 4.0 (older versions)
if NAUTILUS_VERSION is None:
    try:
        require_version('Nautilus', '4.0')
        require_version('Gtk', '4.0')
        require_version('Gdk', '4.0')
        from gi.repository import Nautilus, GObject, Gtk, Gio, Gdk, GLib
        NAUTILUS_VERSION = 4
    except (ValueError, ImportError):
        pass

# Try Nautilus 3.0 (legacy)
if NAUTILUS_VERSION is None:
    try:
        require_version('Nautilus', '3.0')
        require_version('Gtk', '3.0')
        require_version('Gdk', '3.0')
        from gi.repository import Nautilus, GObject, Gtk, Gio, Gdk, GLib
        NAUTILUS_VERSION = 3
    except (ValueError, ImportError) as e:
        _import_error = e

# If no version could be imported, create dummy class to avoid crash
if NAUTILUS_VERSION is None:
    logger.error(f"Could not import Nautilus: {_import_error}")
    logger.error("Extension will not be available.")
    # Create dummy classes so the file loads without error
    class GObject:
        class GObject:
            pass
    class Nautilus:
        class MenuProvider:
            pass
        class MenuItem:
            def __init__(self, **kwargs): pass
            def connect(self, *args): pass


# Wordlist for passphrase generation (~500 common English words, 4-8 letters)
# Based on EFF's diceware wordlist for memorable passphrases
PASSPHRASE_WORDLIST = [
    "about", "above", "acid", "actor", "adopt", "adult", "after", "again",
    "agent", "agree", "ahead", "alarm", "album", "alert", "alien", "alive",
    "alley", "allow", "alone", "alpha", "alter", "amino", "among", "ample",
    "angel", "anger", "angle", "angry", "ankle", "apart", "apple", "apply",
    "arena", "argue", "armor", "arrow", "aside", "asset", "atlas", "audio",
    "audit", "avoid", "award", "bacon", "badge", "badly", "baker", "bases",
    "basic", "basin", "basis", "batch", "beach", "beard", "beast", "began",
    "begin", "begun", "being", "belly", "below", "bench", "berry", "bible",
    "bikes", "birds", "birth", "black", "blade", "blame", "blank", "blast",
    "blaze", "bleed", "blend", "bless", "blind", "blink", "block", "blood",
    "bloom", "blown", "blues", "blunt", "board", "boast", "boats", "bored",
    "bonus", "boost", "booth", "boots", "bound", "boxer", "brain", "brand",
    "brass", "brave", "bread", "break", "breed", "brick", "bride", "brief",
    "bring", "brisk", "broad", "broke", "brook", "brown", "brush", "build",
    "built", "bunch", "burst", "cabin", "cable", "camel", "canal", "candy",
    "canoe", "cards", "cargo", "carry", "carve", "catch", "cause", "cease",
    "cedar", "chain", "chair", "chalk", "champ", "chaos", "charm", "chart",
    "chase", "cheap", "check", "cheek", "chess", "chest", "chief", "child",
    "chill", "china", "chips", "chord", "chose", "chunk", "civic", "civil",
    "claim", "clash", "class", "clean", "clear", "clerk", "click", "cliff",
    "climb", "cling", "cloak", "clock", "clone", "close", "cloth", "cloud",
    "clown", "clubs", "coach", "coast", "codes", "comet", "comic", "coral",
    "could", "count", "coupe", "court", "cover", "crack", "craft", "crane",
    "crash", "crawl", "crazy", "cream", "creek", "creep", "crest", "crime",
    "crisp", "cross", "crowd", "crown", "crude", "cruel", "crush", "cubic",
    "curve", "cycle", "daily", "dairy", "dance", "darts", "dealt", "death",
    "debut", "decal", "decay", "decor", "decoy", "delta", "demon", "denim",
    "dense", "depot", "depth", "derby", "desks", "devil", "diary", "digit",
    "diner", "dirty", "disco", "ditch", "diver", "dodge", "doing", "donor",
    "doubt", "dough", "downs", "dozen", "draft", "drain", "drake", "drama",
    "drank", "drape", "drawl", "drawn", "dream", "dress", "dried", "drift",
    "drill", "drink", "drive", "droit", "drown", "drugs", "drums", "drunk",
    "dusty", "dwarf", "eager", "eagle", "early", "earth", "easel", "eaten",
    "eaves", "ebony", "edges", "eight", "elbow", "elder", "elect", "elite",
    "empty", "ended", "enemy", "enjoy", "enter", "entry", "equal", "equip",
    "error", "erupt", "essay", "evade", "event", "every", "exact", "exams",
    "excel", "exile", "exist", "extra", "fable", "facts", "faint", "fairy",
    "faith", "false", "fancy", "fatal", "fault", "favor", "feast", "fence",
    "ferry", "fetch", "fever", "fiber", "field", "fifth", "fifty", "fight",
    "films", "final", "finds", "fired", "firms", "first", "fixed", "flags",
    "flame", "flank", "flash", "flask", "flock", "flood", "floor", "flora",
    "flour", "fluid", "flush", "flute", "focal", "focus", "foggy", "folks",
    "force", "forge", "forms", "forth", "forum", "fossil", "found", "frame",
    "frank", "fraud", "fresh", "fried", "front", "frost", "fruit", "fully",
    "funds", "funny", "fused", "gains", "gamma", "gauge", "gears", "geese",
    "genre", "ghost", "giant", "gifts", "girls", "given", "gives", "gland",
    "glass", "gleam", "glide", "globe", "glory", "gloss", "glove", "glyph",
    "goals", "goats", "going", "goods", "goose", "grace", "grade", "grain",
    "grand", "grant", "grape", "graph", "grasp", "grass", "grave", "greed",
    "greek", "green", "greet", "grief", "grill", "grind", "grips", "gross",
    "group", "grove", "grown", "guard", "guess", "guest", "guide", "guild",
    "guilt", "habit", "hairs", "hands", "handy", "happy", "hardy", "harms",
    "harsh", "haste", "hasty", "hatch", "haven", "havoc", "hazel", "heads",
    "heals", "heard", "heart", "heavy", "hedge", "heels", "heist", "hello",
    "helps", "herbs", "hints", "hobby", "holds", "holes", "homer", "honey",
    "honor", "hooks", "hopes", "horse", "hosts", "hotel", "hound", "hours",
    "house", "hover", "human", "humid", "humor", "hurry", "icons", "ideal",
    "ideas", "image", "index", "indie", "inner", "input", "intel", "inter",
    "intro", "ionic", "irish", "irony", "issue", "items", "ivory", "jeans",
    "jewel", "joins", "joint", "joker", "jolly", "jones", "judge", "juice",
    "jumbo", "jumps", "kicks", "kinds", "kings", "kites", "knack", "knees",
    "knife", "knock", "knots", "known", "label", "labor", "laced", "lakes",
    "lance", "lands", "lanes", "large", "laser", "lasts", "later", "latex",
    "latin", "laugh", "layer", "leads", "leaks", "leapt", "learn", "lease",
    "least", "leave", "ledge", "legal", "lemon", "level", "lever", "light",
    "liked", "limbs", "limit", "lined", "linen", "liner", "lines", "links",
    "lions", "lists", "lived", "liver", "lives", "loads", "loans", "lobby",
    "local", "locks", "lodge", "lofty", "logic", "logos", "looks", "loops",
    "loose", "lords", "lorry", "loser", "lotus", "loved", "lover", "lower",
    "loyal", "lucky", "lunar", "lunch", "lungs", "lying", "lyric", "macro",
    "magic", "major", "maker", "males", "manor", "maple", "march", "marks",
    "marsh", "masks", "match", "maybe", "mayor", "meals", "means", "media",
    "meets", "melon", "mercy", "merge", "merit", "merry", "messy", "metal",
    "meter", "micro", "might", "miles", "mills", "miner", "minor", "minus",
    "mints", "mixed", "model", "modem", "modes", "moist", "moldy", "money",
    "monks", "month", "moods", "moons", "moral", "motor", "motto", "mount",
    "mouse", "mouth", "moved", "mover", "moves", "movie", "much", "muddy",
    "multi", "mural", "music", "myths", "naive", "named", "names", "nanny",
    "nasty", "naval", "needs", "nerve", "never", "newly", "nexus", "night",
    "ninja", "ninth", "noble", "nodes", "noise", "north", "notch", "noted",
    "notes", "novel", "nurse", "occur", "ocean", "olive", "omega", "onion",
    "opens", "opera", "optic", "orbit", "order", "organ", "other", "ought",
    "outer", "owned", "owner", "oxide", "ozone", "paced", "packs", "pages",
    "pains", "paint", "pairs", "palms", "panel", "panic", "pants", "papal",
    "paper", "parks", "parts", "party", "pasta", "paste", "patch", "paths",
    "patio", "pause", "peace", "peaks", "pearl", "pedal", "penny", "perks",
    "pesos", "petty", "phase", "phone", "photo", "piano", "picks", "piece",
    "piety", "pilot", "pinch", "pines", "pipes", "pitch", "pixel", "pizza",
    "place", "plain", "plane", "plans", "plant", "plate", "plays", "plaza",
    "plead", "plots", "pluck", "plugs", "plumb", "plume", "plump", "plums",
    "plus", "poems", "poets", "point", "poker", "polar", "poles", "polls",
    "ponds", "pools", "porch", "ports", "posed", "poses", "posts", "pouch",
    "pound", "power", "press", "preys", "price", "pride", "prime", "print",
    "prior", "prism", "prize", "probe", "prone", "proof", "props", "prose",
    "proud", "prove", "proxy", "psalm", "pulse", "pumps", "punch", "pupil",
    "puppy", "purse", "queen", "query", "quest", "queue", "quick", "quiet",
    "quilt", "quota", "quote", "radar", "radio", "rails", "rains", "raise",
    "rally", "ranch", "range", "ranks", "rapid", "ratio", "raven", "razor",
    "reach", "reads", "ready", "realm", "rebel", "refer", "reign", "relax",
    "relay", "relic", "remix", "renal", "renew", "repay", "reply", "reset",
    "resin", "retro", "rider", "ridge", "rifle", "right", "rigid", "rings",
    "riots", "risky", "ritzy", "rival", "river", "roads", "roast", "robot",
    "rocks", "rocky", "roger", "roles", "rolls", "roman", "roofs", "rooms",
    "roots", "roses", "rouge", "rough", "round", "route", "royal", "rugby",
    "ruins", "ruled", "ruler", "rules", "rumor", "rural", "rusty", "sadly",
    "safer", "saint", "salad", "sales", "salon", "salsa", "salty", "sands",
    "sandy", "satin", "sauce", "saved", "saves", "scale", "scarf", "scary",
    "scene", "scent", "scope", "score", "scout", "scrap", "seals", "seats",
    "seeds", "seeks", "seems", "seize", "sense", "serve", "setup", "seven",
    "shade", "shaft", "shake", "shall", "shame", "shape", "share", "shark",
    "sharp", "shave", "sheep", "sheer", "sheet", "shelf", "shell", "shift",
    "shine", "shiny", "ships", "shirt", "shock", "shoes", "shoot", "shops",
    "shore", "short", "shots", "shout", "shown", "shows", "sides", "siege",
    "sight", "sigma", "signs", "silly", "since", "sites", "sixth", "sixty",
    "sized", "sizes", "skill", "skins", "skirt", "skull", "slate", "slave",
    "sleek", "sleep", "slice", "slide", "slope", "slump", "small", "smart",
    "smell", "smile", "smoke", "snake", "snaps", "sneak", "snowy", "sober",
    "socks", "solar", "solid", "solve", "songs", "sonic", "sorry", "sorts",
    "souls", "sound", "south", "space", "spare", "spark", "spawn", "speak",
    "spear", "specs", "speed", "spell", "spend", "spent", "spice", "spicy",
    "spike", "spine", "split", "spoke", "spoon", "sport", "spots", "spray",
    "squad", "stack", "staff", "stage", "stain", "stair", "stake", "stamp",
    "stand", "stark", "stars", "start", "state", "stays", "steak", "steal",
    "steam", "steel", "steep", "steer", "stems", "steps", "stick", "stiff",
    "still", "stock", "stomp", "stone", "stood", "stool", "store", "storm",
    "story", "stout", "stove", "strap", "straw", "strip", "stuck", "study",
    "stuff", "style", "sugar", "suite", "sunny", "super", "surge", "swamp",
    "swans", "swear", "sweat", "sweep", "sweet", "swept", "swift", "swing",
    "swiss", "sword", "syrup", "table", "taken", "tales", "talks", "tanks",
    "tapes", "tasks", "taste", "tasty", "taxes", "teach", "teams", "tears",
    "teens", "teeth", "tempo", "tends", "tense", "tenor", "tenth", "terms",
    "tests", "texas", "texts", "thank", "theft", "theme", "thick", "thief",
    "thing", "think", "third", "those", "three", "threw", "throw", "thumb",
    "tiger", "tight", "tiles", "timer", "times", "tints", "tired", "titan",
    "title", "toast", "today", "token", "tombs", "toned", "tones", "tools",
    "tooth", "topic", "torch", "total", "touch", "tough", "tours", "tower",
    "towns", "toxic", "trace", "track", "tract", "trade", "trail", "train",
    "trait", "trash", "treat", "trees", "trend", "trial", "tribe", "trick",
    "tried", "tries", "trims", "trips", "troop", "truck", "truly", "trump",
    "trunk", "trust", "truth", "tulip", "tumor", "tunes", "turbo", "turns",
    "tutor", "tweed", "twice", "twins", "twist", "typed", "types", "uncle",
    "under", "unify", "union", "unite", "units", "unity", "until", "upper",
    "urban", "urged", "usage", "users", "using", "usual", "valid", "value",
    "valve", "vault", "vegas", "venom", "venue", "venus", "verbs", "verse",
    "video", "views", "vinyl", "viola", "viral", "virus", "visit", "vista",
    "vital", "vivid", "vocal", "vodka", "voice", "volts", "voted", "voter",
    "votes", "wages", "wagon", "waist", "walks", "walls", "waltz", "wants",
    "waste", "watch", "water", "watts", "waves", "wears", "weary", "weeds",
    "weeks", "weird", "wells", "welsh", "whale", "wheat", "wheel", "where",
    "which", "while", "white", "whole", "whose", "widen", "wider", "width",
    "winds", "wines", "wings", "wiped", "wires", "witch", "wives", "woman",
    "women", "woods", "words", "works", "world", "worms", "worry", "worse",
    "worst", "worth", "would", "wound", "woven", "wrath", "wreck", "wrist",
    "write", "wrong", "wrote", "yacht", "yards", "years", "yeast", "yield",
    "young", "yours", "youth", "zebra", "zeros", "zesty", "zones"
]


class AgeEncryptionExtension(GObject.GObject, Nautilus.MenuProvider):
    """Main Nautilus extension for age encryption"""

    def __init__(self) -> None:
        super().__init__()
        self._dependencies_checked: bool = False
        self._age_available: Optional[bool] = None
        # Cache for mat2 availability check
        self._mat2_checked: bool = False
        self._mat2_available: Optional[bool] = None
        # Rate limiting: track failed decryption attempts per file
        self._failed_attempts: Dict[str, List[float]] = defaultdict(list)

    def validate_path(self, path: str) -> bool:
        """Validate that a path is safe (no traversal attacks).

        Args:
            path: The path to validate

        Returns:
            True if the path is safe, False otherwise
        """
        # Must be absolute path
        if not os.path.isabs(path):
            logger.warning(f"Path validation failed: not absolute: {path}")
            return False

        # Resolve the path to catch symlink attacks
        try:
            resolved = os.path.realpath(path)
        except (OSError, ValueError) as e:
            logger.warning(f"Path validation failed: cannot resolve: {e}")
            return False

        # Check for path traversal (.. components after resolution)
        # A resolved path should not contain '..'
        if '..' in resolved.split(os.sep):
            logger.warning(f"Path validation failed: traversal detected: {path}")
            return False

        # Don't allow operations on critical system directories
        dangerous_prefixes = ['/bin', '/sbin', '/usr', '/etc', '/var', '/boot', '/root']
        for prefix in dangerous_prefixes:
            if resolved.startswith(prefix + os.sep) or resolved == prefix:
                logger.warning(f"Path validation failed: system directory: {resolved}")
                return False

        return True

    def check_rate_limit(self, file_path: str) -> bool:
        """Check if decryption is rate limited for this file.

        Args:
            file_path: Path to the file being decrypted

        Returns:
            True if allowed to proceed, False if rate limited
        """
        now = time.time()
        attempts = self._failed_attempts[file_path]

        # Clean old attempts (outside the window)
        attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
        self._failed_attempts[file_path] = attempts

        if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
            last_attempt = attempts[-1]
            wait_time = RATE_LIMIT_LOCKOUT_SECONDS - (now - last_attempt)
            if wait_time > 0:
                self.show_error("Rate Limited",
                    f"Too many failed attempts.\nWait {int(wait_time)} seconds.")
                return False
        return True

    def record_failed_attempt(self, file_path: str) -> None:
        """Record a failed decryption attempt for rate limiting."""
        self._failed_attempts[file_path].append(time.time())

    def clear_failed_attempts(self, file_path: str) -> None:
        """Clear failed attempts after successful decryption."""
        self._failed_attempts.pop(file_path, None)

    def check_dependencies(self) -> bool:
        """Verify that age is installed (lazy check)"""
        if self._dependencies_checked:
            return self._age_available

        self._dependencies_checked = True
        try:
            subprocess.run(['age', '--version'],
                         capture_output=True,
                         check=True,
                         timeout=2)
            self._age_available = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            self._age_available = False

        return self._age_available

    def check_mat2_installed(self) -> bool:
        """Check if mat2 (metadata anonymisation toolkit) is available (lazy check with cache).

        Returns:
            True if mat2 is available, False otherwise
        """
        if self._mat2_checked:
            return self._mat2_available

        self._mat2_checked = True
        try:
            subprocess.run(
                ['mat2', '--version'],
                capture_output=True,
                check=True,
                timeout=2
            )
            self._mat2_available = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            self._mat2_available = False

        return self._mat2_available

    def get_file_items(self, *args) -> List:
        """Entry point for context menu items"""
        # If Nautilus was not imported correctly, don't show menu
        if NAUTILUS_VERSION is None:
            return []

        # Verify dependencies (lazy check)
        if not self.check_dependencies():
            # Only show error once per session
            if not hasattr(self, '_error_shown'):
                self._error_shown = True
                self.show_error("age is not installed",
                              "Install age to use this extension:\n\n"
                              "sudo apt install age")
            return []

        # Compatibility between Nautilus 3 and 4
        if len(args) == 1:  # Nautilus 4
            files = args[0]
        else:  # Nautilus 3
            files = args[1]

        if not files:
            return []
        
        # Convert URIs to paths
        paths = []
        for file_info in files:
            if hasattr(file_info, 'get_uri'):
                uri = file_info.get_uri()
                path = self.get_path_from_uri(uri)
                if path:
                    paths.append(path)

        if not paths:
            return []
        
        items = []

        # Detect if all files are .age
        all_age_files = all(p.endswith('.age') for p in paths)

        if all_age_files:
            # Menu for decryption
            items.append(self.create_decrypt_menu_item(paths))
        else:
            # Menu for encryption (handles both files and folders)
            items.append(self.create_encrypt_menu_item(paths))

            # Add HSM option if PKCS#11 module is available
            if self.find_pkcs11_module():
                items.append(self.create_encrypt_hsm_menu_item(paths))

        return items
    
    def create_encrypt_menu_item(self, paths: List[str]) -> 'Nautilus.MenuItem':
        """Create menu item for encryption (files and/or folders)"""
        # Count files and folders
        num_files = sum(1 for p in paths if os.path.isfile(p))
        num_folders = sum(1 for p in paths if os.path.isdir(p))

        if len(paths) == 1:
            if num_folders == 1:
                label = "Encrypt folder with age"
            else:
                label = "Encrypt with age"
        else:
            parts = []
            if num_files > 0:
                parts.append(f"{num_files} file{'s' if num_files > 1 else ''}")
            if num_folders > 0:
                parts.append(f"{num_folders} folder{'s' if num_folders > 1 else ''}")
            label = f"Encrypt {' + '.join(parts)} with age"

        item = Nautilus.MenuItem(
            name='AgeExtension::EncryptItems',
            label=label,
            tip='Encrypt with age (ChaCha20-Poly1305)'
        )
        item.connect('activate', lambda menu, p=list(paths): self.on_encrypt_items(menu, p))
        return item

    def create_encrypt_hsm_menu_item(self, paths: List[str]) -> 'Nautilus.MenuItem':
        """Create menu item for HSM-based encryption.

        Only shown when PKCS#11 module (SafeNet eToken) is detected.
        """
        # Count files and folders for dynamic label
        num_files = sum(1 for p in paths if os.path.isfile(p))
        num_folders = sum(1 for p in paths if os.path.isdir(p))

        if len(paths) == 1:
            if num_folders == 1:
                label = "Encrypt folder with HSM"
            else:
                label = "Encrypt with HSM"
        else:
            parts = []
            if num_files > 0:
                parts.append(f"{num_files} file{'s' if num_files > 1 else ''}")
            if num_folders > 0:
                parts.append(f"{num_folders} folder{'s' if num_folders > 1 else ''}")
            label = f"Encrypt {' + '.join(parts)} with HSM"

        item = Nautilus.MenuItem(
            name='AgeExtension::EncryptItemsHSM',
            label=label,
            tip='Encrypt using SafeNet token TRNG (hardware random)'
        )
        item.connect('activate', lambda menu, p=list(paths): self.on_encrypt_items_hsm(menu, p))
        return item

    def create_decrypt_menu_item(self, paths: List[str]) -> 'Nautilus.MenuItem':
        """Create menu item for decryption"""
        if len(paths) == 1:
            label = "Decrypt with age"
        else:
            label = f"Decrypt {len(paths)} files with age"

        item = Nautilus.MenuItem(
            name='AgeExtension::DecryptFiles',
            label=label,
            tip='Decrypt .age file(s)'
        )
        item.connect('activate', lambda menu, p=list(paths): self.on_decrypt_files(menu, p))
        return item

    def get_path_from_uri(self, uri: str) -> str:
        """Convert URI to system path"""
        try:
            parsed = urlparse(uri)
            path = unquote(parsed.path)
            return path
        except (ValueError, TypeError) as e:
            logger.warning(f"URI parsing error: {e}")
            return None
    
    def on_encrypt_items(self, menu: 'Nautilus.MenuItem', paths: List[str]) -> None:
        """Handler for encrypting files and/or folders.

        Launches a completely separate process to avoid blocking Nautilus.
        The subprocess handles dialog, mat2, tar, and age encryption.
        Returns immediately so Nautilus stays responsive.
        """
        script_path = os.path.realpath(__file__)
        paths_json = json.dumps(paths)
        subprocess.Popen(
            [sys.executable, script_path, '--encrypt', paths_json],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Returns IMMEDIATELY - Nautilus stays 100% responsive

    # === HSM Encryption Handlers ===

    def on_encrypt_items_hsm(self, menu: 'Nautilus.MenuItem', paths: List[str]) -> None:
        """Handler for encrypting files/folders using HSM-generated passphrase.

        Launches a completely separate process to avoid blocking Nautilus.
        Returns immediately so Nautilus stays responsive.
        """
        script_path = os.path.realpath(__file__)
        paths_json = json.dumps(paths)
        subprocess.Popen(
            [sys.executable, script_path, '--hsm', paths_json],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Returns IMMEDIATELY - Nautilus stays 100% responsive

    def _ask_hsm_confirmation(self, passphrase: str) -> Optional[bool]:
        """Show HSM passphrase and ask for confirmation.

        Args:
            passphrase: The HSM-generated passphrase to display

        Returns:
            True if user wants to delete originals, False if keep, None if cancelled
        """
        try:
            # Copy to clipboard first
            self.copy_to_clipboard(passphrase)

            # Word wrap passphrase for display (insert newlines every 70 chars)
            wrapped = '\n'.join(passphrase[i:i+70] for i in range(0, len(passphrase), 70))

            zenity_process = subprocess.Popen(
                ['zenity', '--question',
                 '--title', 'HSM Passphrase',
                 '--text', '📋 HSM Passphrase copied to clipboard!\n\n'
                          f'<tt>{wrapped}</tt>\n\n'
                          '🔒 Generated from hardware TRNG\n\n'
                          '⚠️ Save this passphrase somewhere safe NOW!',
                 '--ok-label', 'Encrypt (keep original)',
                 '--cancel-label', 'Cancel',
                 '--extra-button', 'Encrypt & Delete original',
                 '--width', '600'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, _ = zenity_process.communicate(timeout=300)
            returncode = zenity_process.returncode

            if returncode == 0:
                return False  # Keep originals
            elif 'Delete' in stdout:
                return True  # Delete originals
            else:
                return None  # Cancelled

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            if 'zenity_process' in locals():
                zenity_process.kill()
            return None

    def on_decrypt_files(self, menu: 'Nautilus.MenuItem', paths: List[str]) -> None:
        """Handler for decrypting files.

        Launches a completely separate process to avoid blocking Nautilus.
        Returns immediately so Nautilus stays responsive.
        """
        script_path = os.path.realpath(__file__)
        paths_json = json.dumps(paths)
        subprocess.Popen(
            [sys.executable, script_path, '--decrypt', paths_json],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Returns IMMEDIATELY - Nautilus stays 100% responsive

    def encrypt_file(self, input_path: str, output_path: str, password: str) -> bool:
        """Encrypt a file with age securely using PTY"""
        master_fd = None
        slave_fd = None
        process = None
        try:
            # age requires a TTY to read passwords interactively
            # We use pty to simulate a terminal
            master_fd, slave_fd = pty.openpty()

            process = subprocess.Popen(
                ['age', '-p', '-o', output_path, input_path],
                stdin=slave_fd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Close slave in parent process
            os.close(slave_fd)
            slave_fd = None

            # Small pause for age to be ready to receive input
            time.sleep(0.1)

            # age -p asks for password twice (entry + confirmation)
            # Security note: password is written directly to PTY fd, never logged
            os.write(master_fd, f"{password}\n".encode('utf-8'))
            time.sleep(0.1)
            os.write(master_fd, f"{password}\n".encode('utf-8'))

            # 120s timeout - age encryption is fast, longer waits indicate problems
            stdout, stderr = process.communicate(timeout=120)

            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                err_msg = stderr.decode('utf-8', errors='replace')
                logger.error(f"Age encryption failed (code {process.returncode}): {err_msg}")
                # Clean up partial output file if exists
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                return False

        except subprocess.TimeoutExpired:
            logger.error("Encryption timeout")
            if process:
                process.kill()
                process.wait()  # Prevent zombie process
            return False
        except OSError as e:
            logger.error(f"Encryption OS error: {e}")
            return False
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return False
        finally:
            # Clean up file descriptors
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass

    def decrypt_file(self, input_path: str, output_path: str, password: str) -> bool:
        """Decrypt a .age file securely using PTY"""
        import time
        master_fd = None
        slave_fd = None
        process = None
        try:
            # age requires a TTY to read passwords interactively
            # We use pty to simulate a terminal
            master_fd, slave_fd = pty.openpty()

            process = subprocess.Popen(
                ['age', '-d', '-o', output_path, input_path],
                stdin=slave_fd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Close slave in parent process
            os.close(slave_fd)
            slave_fd = None

            # Small pause for age to be ready to receive input
            time.sleep(0.1)

            # age -d asks for password once
            # Security note: password is written directly to PTY fd, never logged
            os.write(master_fd, f"{password}\n".encode('utf-8'))

            # 120s timeout - age decryption is fast, longer waits indicate problems
            stdout, stderr = process.communicate(timeout=120)

            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                err_msg = stderr.decode('utf-8', errors='replace')
                logger.error(f"Age decryption failed (code {process.returncode}): {err_msg}")
                # Delete failed output file
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                return False

        except subprocess.TimeoutExpired:
            logger.error("Decryption timeout")
            if process:
                process.kill()
                process.wait()  # Prevent zombie process
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False
        except OSError as e:
            logger.error(f"Decryption OS error: {e}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False
        finally:
            # Clean up file descriptors
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass

    def verify_age_file(self, file_path: str) -> bool:
        """Verify if a file is a valid .age file"""
        try:
            # Read age file header
            with open(file_path, 'rb') as f:
                header = f.read(100)
                # age files start with "age-encryption.org/v1"
                return b'age-encryption.org/v1' in header
        except (OSError, IOError) as e:
            logger.warning(f"File verification error: {e}")
            return False

    def secure_delete(self, file_path: str) -> None:
        """Delete a file securely using shred"""
        try:
            # -v: verbose, -f: force, -z: add final zero pass, -u: REMOVE file after
            # -n 3: 3 passes (sufficient for SSDs, 10 is excessive)
            subprocess.run(
                ['shred', '-vfzu', '-n', '3', file_path],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Secure delete error: {e}")
            # Fallback to normal rm if shred fails
            try:
                os.remove(file_path)
            except OSError as rm_error:
                logger.error(f"Fallback delete also failed: {rm_error}")

    def clean_metadata(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Clean metadata from a file using mat2, preserving original.

        Creates a temporary copy with cleaned metadata.
        Caller is responsible for deleting the temp file after use.

        Args:
            file_path: Path to the original file (will NOT be modified)

        Returns:
            Tuple of (cleaned_temp_path, error_message)
            - (path, None) if successful - path to cleaned temp file
            - (None, "error") if failed
        """
        if not self.validate_path(file_path):
            return (None, "Invalid file path")

        if not os.path.isfile(file_path):
            return (None, "Not a file")

        temp_path = None
        try:
            # Create temp file with same extension to preserve format
            _, ext = os.path.splitext(file_path)
            fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='age_clean_')
            os.close(fd)

            # Copy original to temp (preserves content but not necessarily all metadata)
            shutil.copy2(file_path, temp_path)

            # Clean metadata on temp copy only
            result = subprocess.run(
                ['mat2', '--inplace', '--unknown-members', 'omit', temp_path],
                capture_output=True,
                timeout=60,
                text=True
            )

            # mat2 return codes:
            # 0 = success (metadata cleaned)
            # 1 = file format not supported (keep copy as-is, still use it)
            if result.returncode in (0, 1):
                logger.info(f"Metadata cleaned: {file_path} -> {temp_path}")
                return (temp_path, None)
            else:
                # Cleanup on error
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                err_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.warning(f"mat2 failed on {file_path}: {err_msg}")
                return (None, err_msg)

        except subprocess.TimeoutExpired:
            logger.error(f"mat2 timeout on: {file_path}")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return (None, "Timeout cleaning metadata")

        except FileNotFoundError:
            logger.error("mat2 not found")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return (None, "mat2 not installed")

        except OSError as e:
            logger.error(f"mat2 error on {file_path}: {e}")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return (None, str(e))

    def ask_password(self, title: str, text: str) -> str:
        """Ask for a password using zenity"""
        try:
            result = subprocess.run(
                ['zenity', '--password',
                 '--title', title,
                 '--text', text],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    def generate_passphrase(self, num_words: int = 24) -> str:
        """Generate a secure passphrase using cryptographically secure random selection.

        Args:
            num_words: Number of words in the passphrase (default: 24)

        Returns:
            A passphrase like "tiger-ocean-mountain-castle-brave-..."
        """
        words = [secrets.choice(PASSPHRASE_WORDLIST) for _ in range(num_words)]
        return '-'.join(words)

    # === PKCS#11 HSM Support Functions ===

    def validate_pkcs11_module_path(self, path: str) -> bool:
        """Validate that a PKCS#11 module path is safe.

        Only allows modules from the predefined whitelist to prevent
        loading arbitrary shared libraries.

        Args:
            path: Path to validate

        Returns:
            True if path is in the allowed whitelist, False otherwise
        """
        if not path:
            return False
        # Only allow paths from our whitelist (case-sensitive exact match)
        return path in PKCS11_MODULE_PATHS

    def validate_hsm_pin(self, pin: str) -> Tuple[bool, str]:
        """Validate HSM PIN format.

        SafeNet tokens typically accept 4-16 character PINs.

        Args:
            pin: PIN to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not pin:
            return (False, "PIN cannot be empty")
        if len(pin) < 4:
            return (False, "PIN too short (minimum 4 characters)")
        if len(pin) > 16:
            return (False, "PIN too long (maximum 16 characters)")
        # Basic sanity: only printable ASCII (no control characters)
        if not all(32 <= ord(c) <= 126 for c in pin):
            return (False, "PIN contains invalid characters")
        return (True, "")

    def find_pkcs11_module(self) -> Optional[str]:
        """Find installed PKCS#11 module path (SafeNet eToken).

        Checks multiple common installation paths for the SafeNet
        eToken driver.

        Returns:
            Path to libeToken.so if found, None otherwise
        """
        for path in PKCS11_MODULE_PATHS:
            if os.path.exists(path):
                return path
        return None

    def is_hsm_token_present(self, module_path: str) -> bool:
        """Check if HSM token is physically connected.

        Uses pkcs11-tool to query the token slots.

        Args:
            module_path: Path to the PKCS#11 module (.so file)

        Returns:
            True if a token is present in any slot, False otherwise
        """
        # Security: validate module path is in whitelist
        if not self.validate_pkcs11_module_path(module_path):
            logger.warning("Invalid PKCS#11 module path rejected")
            return False

        try:
            result = subprocess.run(
                ['pkcs11-tool', '--module', module_path, '--list-slots'],
                capture_output=True,
                timeout=5
            )
            # Check for token presence indicators in output
            output = result.stdout.lower()
            return b'token present' in output or (result.returncode == 0 and b'slot' in output)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def ask_hsm_pin(self) -> Optional[str]:
        """Ask user for HSM token PIN using zenity.

        Returns:
            The PIN entered by the user, or None if cancelled
        """
        try:
            result = subprocess.run(
                ['zenity', '--password',
                 '--title', '🔐 HSM Token PIN',
                 '--text', 'Enter your SafeNet token PIN:'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def generate_passphrase_from_hsm(self, module_path: str, pin: str) -> Optional[str]:
        """Generate passphrase using HSM's True Random Number Generator.

        Uses pkcs11-tool to generate cryptographically secure random bytes
        from the hardware token's TRNG, then encodes them as Base64.

        Args:
            module_path: Path to the PKCS#11 module
            pin: User's PIN for the token

        Returns:
            Base64-encoded passphrase (43 chars) or None on failure
        """
        # Security: validate module path is in whitelist
        if not self.validate_pkcs11_module_path(module_path):
            logger.warning("Invalid PKCS#11 module path rejected")
            return None

        tmp_path = None
        process = None

        try:
            # Create secure temporary file with restrictive umask
            old_umask = os.umask(0o077)  # Only owner can access new files
            try:
                fd, tmp_path = tempfile.mkstemp(prefix='hsm_random_', suffix='.bin')
                os.close(fd)
                os.chmod(tmp_path, 0o600)  # Explicitly ensure only owner can read
            finally:
                os.umask(old_umask)  # Restore original umask

            # Use --pin option (pkcs11-tool's util_getpass doesn't work with PTY)
            # Note: PIN briefly visible in /proc/<pid>/cmdline but process is short-lived
            process = subprocess.Popen(
                ['pkcs11-tool', '--module', module_path,
                 '--login', '--pin', pin,
                 '--generate-random', str(PKCS11_RANDOM_BYTES),
                 '--output-file', tmp_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for completion
            stdout, stderr = process.communicate(timeout=PKCS11_TIMEOUT)

            if process.returncode != 0:
                # Log detailed error internally but don't expose to user
                # (prevents information leakage about HSM internals)
                logger.warning("PKCS#11 operation failed (check PIN or token)")
                return None

            # Read generated random bytes
            with open(tmp_path, 'rb') as f:
                random_bytes = f.read()

            if len(random_bytes) != PKCS11_RANDOM_BYTES:
                # Generic message to avoid leaking HSM implementation details
                logger.warning("HSM random generation failed (unexpected output)")
                return None

            # Encode as URL-safe Base64 without padding (43 characters)
            passphrase = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
            return passphrase

        except subprocess.TimeoutExpired:
            logger.error("HSM timeout generating random")
            if process:
                process.kill()
                process.wait()  # Prevent zombie
            return None
        except Exception as e:
            logger.error(f"HSM generation failed: {e}")
            return None
        finally:
            # Secure cleanup of temporary file containing HSM random bytes
            # CRITICAL: This file must be destroyed - it contains key material
            if tmp_path:
                try:
                    # First: overwrite with zeros (in case shred fails)
                    if os.path.exists(tmp_path):
                        with open(tmp_path, 'wb') as f:
                            f.write(b'\x00' * PKCS11_RANDOM_BYTES)
                            f.flush()
                            os.fsync(f.fileno())  # Force write to disk
                except OSError:
                    pass

                # Then: secure delete with shred
                try:
                    self.secure_delete(tmp_path)
                except (FileNotFoundError, OSError):
                    pass

                # Final fallback: force remove if still exists
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                        logger.warning("HSM temp file required fallback deletion")
                except OSError:
                    logger.error("CRITICAL: Could not delete HSM temp file!")

    def copy_to_clipboard(self, text: str) -> bool:
        """Copy text to system clipboard (Wayland optimized).

        Uses wl-copy directly for Wayland.

        Args:
            text: Text to copy to clipboard

        Returns:
            True if clipboard copy succeeded, False otherwise
        """
        try:
            process = subprocess.Popen(
                ['wl-copy'],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            process.communicate(input=text.encode('utf-8'), timeout=1)
            return process.returncode == 0
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False

    def ask_password_method(self) -> Tuple[Optional[str], bool, bool]:
        """Generate secure passphrase for encryption.

        No manual password option - always generates secure passphrase
        for maximum security.

        Returns:
            Tuple of (passphrase, confirmed, delete_original)
            - passphrase: The generated passphrase or None if cancelled
            - confirmed: True if user clicked Encrypt or Encrypt & Delete
            - delete_original: True if user clicked Encrypt & Delete
        """
        # Generate passphrase automatically
        passphrase = self.generate_passphrase()

        # Show zenity dialog FIRST (non-blocking start) for faster perceived response
        # Clipboard copy happens in parallel while dialog renders
        try:
            zenity_process = subprocess.Popen(
                ['zenity', '--question',
                 '--title', '🔐 Secure Passphrase',
                 '--text', '📋 Passphrase copied to clipboard!\n\n'
                          f'<tt><b>{passphrase}</b></tt>\n\n'
                          '⚠️ Save this passphrase somewhere safe NOW!',
                 '--ok-label', '🔒 Encrypt (keep original)',
                 '--cancel-label', 'Cancel',
                 '--extra-button', '🔒🗑️ Encrypt & Delete original',
                 '--width', '550'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Copy to clipboard IN PARALLEL while zenity dialog is rendering
            self.copy_to_clipboard(passphrase)

            # Wait for user response
            stdout, _ = zenity_process.communicate(timeout=300)
            returncode = zenity_process.returncode

            # Check which button was pressed
            if returncode == 0:
                # OK button (Encrypt without delete)
                return (passphrase, True, False)
            elif 'Delete' in stdout:
                # Extra button (Encrypt & Delete)
                return (passphrase, True, True)
            else:
                # Cancel
                return (None, False, False)

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            if 'zenity_process' in locals():
                zenity_process.kill()
            return (None, False, False)

    def ask_yes_no(self, title: str, text: str) -> bool:
        """Ask yes/no question using zenity"""
        try:
            result = subprocess.run(
                ['zenity', '--question',
                 '--title', title,
                 '--text', text,
                 '--width', '350'],
                timeout=300
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def show_notification(self, title: str, message: str) -> None:
        """Show a system notification (non-blocking)"""
        try:
            subprocess.Popen(
                ['notify-send', '-i', 'dialog-information',
                 title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except (FileNotFoundError, OSError):
            pass

    def show_error(self, title: str, message: str) -> None:
        """Show an error dialog"""
        try:
            subprocess.run(
                ['zenity', '--error',
                 '--title', title,
                 '--text', message,
                 '--width', '400'],
                timeout=60
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Fallback to logger if zenity is not available
            logger.error(f"Dialog error: {title} - {message}")


# ==============================================================================
# CLI Mode - Standalone execution for subprocess calls from Nautilus
# ==============================================================================
# When Nautilus calls on_encrypt_items/on_decrypt_files/on_encrypt_items_hsm,
# they spawn this script as a separate process. This completely avoids GIL
# contention with Nautilus's GLib main loop, preventing "slow application" dialogs.

def standalone_encrypt(paths: List[str]) -> None:
    """Standalone encryption - runs in separate process from Nautilus.

    Args:
        paths: List of file/folder paths to encrypt
    """
    ext = AgeEncryptionExtension()

    # 1. Ask for passphrase (blocks this process, not Nautilus)
    password, _, delete_originals = ext.ask_password_method()
    if not password:
        return

    # 2. Check mat2 availability
    clean_metadata = ext.check_mat2_installed()

    # 3. Show notification that work is starting
    ext.show_notification("Encrypting...",
        f"Processing {len(paths)} item(s)...\n"
        "A notification will appear when done.")

    # 4. Do encryption work (inline, no callback needed in standalone mode)
    temp_dir = None
    tar_path = None

    try:
        # Create temp directory
        temp_dir = tempfile.mkdtemp(prefix='age_bundle_')

        # Copy all items to temp using external cp command
        for item_path in paths:
            item_path = os.path.normpath(item_path)
            if not os.path.exists(item_path):
                raise FileNotFoundError(f"Source path does not exist: {item_path}")
            basename = os.path.basename(item_path)
            dest = os.path.join(temp_dir, basename)
            result = subprocess.run(
                ['cp', '-a', '--', item_path, dest],
                capture_output=True
            )
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')
                raise RuntimeError(f"cp failed for {item_path}: {stderr}")

        # Clean metadata from all files in temp (single pass)
        cleaned_count = 0
        if clean_metadata:
            all_files = []
            for root, dirs, files in os.walk(temp_dir):
                for filename in files:
                    all_files.append(os.path.join(root, filename))

            if all_files:
                for fp in all_files:
                    try:
                        mat2_result = subprocess.run(
                            ['mat2', '--inplace', '--unknown-members', 'omit', fp],
                            capture_output=True, timeout=5
                        )
                        if mat2_result.returncode in (0, 1):
                            cleaned_count += 1
                    except (subprocess.TimeoutExpired, OSError):
                        pass

        # Determine output name and location
        output_dir = os.path.dirname(os.path.normpath(paths[0]))
        if len(paths) == 1:
            bundle_name = os.path.basename(os.path.normpath(paths[0]))
        else:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            bundle_name = f"encrypted_bundle_{timestamp}"

        # Create tar.gz in a SEPARATE temp location (not inside temp_dir!)
        # This avoids tar trying to include itself in the archive
        tar_fd, tar_path = tempfile.mkstemp(suffix='.tar.gz', prefix='age_archive_')
        os.close(tar_fd)  # Close FD, we'll use the path with tar
        result = subprocess.run([
            'tar', '-czf', tar_path, '-C', temp_dir, '.'
        ], capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"tar failed: {stderr}")

        # Encrypt to TEMP directory first (write-then-move pattern)
        temp_encrypted = os.path.join(temp_dir, f"{bundle_name}.age")
        success = ext.encrypt_file(tar_path, temp_encrypted, password)

        # Cleanup tar immediately
        try:
            os.remove(tar_path)
            tar_path = None
        except FileNotFoundError:
            tar_path = None

        # Move encrypted file to final destination
        encrypted_path = None
        if success:
            encrypted_path = os.path.join(output_dir, f"{bundle_name}.age")
            shutil.move(temp_encrypted, encrypted_path)

        # Delete originals if requested
        if success and delete_originals:
            for item_path in paths:
                item_path = os.path.normpath(item_path)
                if os.path.isfile(item_path):
                    ext.secure_delete(item_path)
                elif os.path.isdir(item_path):
                    if ext.validate_path(item_path):
                        shutil.rmtree(item_path)

        # Show result notification
        if success:
            msg = f"✅ {len(paths)} item(s) → {os.path.basename(encrypted_path)}"
            if clean_metadata and cleaned_count > 0:
                msg += f" ({cleaned_count} cleaned)"
            if delete_originals:
                msg += " (originals deleted)"
            subprocess.Popen(
                ['notify-send', '-i', 'security-high', 'Encryption Complete', msg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ['notify-send', '-i', 'dialog-error', '-u', 'critical',
                 'Encryption Failed', 'Could not complete encryption.'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    except Exception as e:
        error_msg = str(e)[:200]  # Truncate long errors for notification
        logger.error(f"Standalone encryption error: {e}")
        subprocess.Popen(
            ['notify-send', '-i', 'dialog-error', '-u', 'critical',
             'Encryption Failed', error_msg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    finally:
        if tar_path:
            try:
                os.remove(tar_path)
            except (FileNotFoundError, OSError):
                pass
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except (FileNotFoundError, OSError):
                pass


def standalone_decrypt(paths: List[str]) -> None:
    """Standalone decryption - runs in separate process from Nautilus.

    Args:
        paths: List of .age file paths to decrypt
    """
    ext = AgeEncryptionExtension()

    # Check rate limit for all files before proceeding
    for file_path in paths:
        if not ext.check_rate_limit(file_path):
            return

    # Verify files first
    invalid_files: List[str] = []
    for file_path in paths:
        if not ext.verify_age_file(file_path):
            invalid_files.append(os.path.basename(file_path))

    if invalid_files:
        ext.show_error("Invalid files",
                      "Not valid .age files:\n" + "\n".join(invalid_files))
        return

    # Ask for password
    password = ext.ask_password("🔓 Decrypt", "Enter password:")
    if not password:
        return

    success_count: int = 0
    fail_count: int = 0

    for file_path in paths:
        # Use hidden temp file to avoid name collision with extracted content
        output_dir = os.path.dirname(file_path)
        temp_decrypted = os.path.join(output_dir, f".{os.path.basename(file_path)}.tmp")

        if ext.decrypt_file(file_path, temp_decrypted, password):
            success_count += 1
            ext.clear_failed_attempts(file_path)

            # Check if decrypted file is a gzip archive (magic bytes: 1f 8b)
            is_gzip = False
            try:
                with open(temp_decrypted, 'rb') as f:
                    magic = f.read(2)
                    is_gzip = (magic == b'\x1f\x8b')
            except (IOError, OSError):
                pass

            # If it's a tar.gz, extract automatically with security validation
            if is_gzip:
                try:
                    # Security: Validate tar contents before extraction
                    list_result = subprocess.run(
                        ['tar', '-tzf', temp_decrypted],
                        capture_output=True, text=True, timeout=60
                    )
                    if list_result.returncode == 0:
                        for member in list_result.stdout.splitlines():
                            if member.startswith('/') or '..' in member:
                                raise ValueError(f"Suspicious path in archive: {member}")

                    # Extract to output directory
                    subprocess.run([
                        'tar', '-xzf', temp_decrypted, '-C', output_dir
                    ], check=True, capture_output=True)

                    # Remove temp file
                    os.remove(temp_decrypted)
                except subprocess.CalledProcessError as e:
                    if os.path.exists(temp_decrypted):
                        os.remove(temp_decrypted)
                    ext.show_error("Error", f"Extraction failed: {e}")
            else:
                # Not a gzip - rename temp to final name
                final_path = file_path[:-4] if file_path.endswith('.age') else f"{file_path}.decrypted"
                os.rename(temp_decrypted, final_path)
        else:
            fail_count += 1
            ext.record_failed_attempt(file_path)
            if os.path.exists(temp_decrypted):
                os.remove(temp_decrypted)

    if success_count > 0:
        ext.show_notification("Done", f"✅ {success_count} file(s) decrypted")

    if fail_count > 0:
        ext.show_error("Error", f"Failed: {fail_count} file(s). Check password.")


def standalone_hsm(paths: List[str]) -> None:
    """Standalone HSM encryption - runs in separate process from Nautilus.

    Args:
        paths: List of file/folder paths to encrypt with HSM
    """
    ext = AgeEncryptionExtension()

    # 1. Find PKCS#11 module
    module_path = ext.find_pkcs11_module()
    if not module_path:
        ext.show_error("HSM Not Found",
            "SafeNet eToken driver not installed.\n"
            "Install libeToken.so and try again.")
        return

    # 2. Verify token is connected
    if not ext.is_hsm_token_present(module_path):
        ext.show_error("Token Not Connected",
            "Please insert your SafeNet token and try again.")
        return

    # 3. Ask for PIN
    pin = ext.ask_hsm_pin()
    if not pin:
        return

    # 3b. Validate PIN format
    pin_valid, pin_error = ext.validate_hsm_pin(pin)
    if not pin_valid:
        ext.show_error("Invalid PIN", pin_error)
        return

    # 4. Generate passphrase from HSM TRNG
    ext.show_notification("Generating...", "Getting random from HSM...")
    passphrase = ext.generate_passphrase_from_hsm(module_path, pin)

    if not passphrase:
        ext.show_error("HSM Error",
            "Failed to generate random from token.\n"
            "Check PIN and try again.")
        return

    # 5. Copy passphrase to clipboard and ask for confirmation
    delete_originals = ext._ask_hsm_confirmation(passphrase)
    if delete_originals is None:
        return  # User cancelled

    # 6. Check mat2 availability
    clean_metadata = ext.check_mat2_installed()

    # 7. Show notification that work is starting
    ext.show_notification("Encrypting (HSM)...",
        f"Processing {len(paths)} item(s) with hardware encryption...")

    # 8. Do encryption work (same as standalone_encrypt but with HSM passphrase)
    temp_dir = None
    tar_path = None

    try:
        temp_dir = tempfile.mkdtemp(prefix='age_bundle_')

        for item_path in paths:
            item_path = os.path.normpath(item_path)
            if not os.path.exists(item_path):
                raise FileNotFoundError(f"Source path does not exist: {item_path}")
            basename = os.path.basename(item_path)
            dest = os.path.join(temp_dir, basename)
            result = subprocess.run(
                ['cp', '-a', '--', item_path, dest],
                capture_output=True
            )
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')
                raise RuntimeError(f"cp failed for {item_path}: {stderr}")

        cleaned_count = 0
        if clean_metadata:
            all_files = []
            for root, dirs, files in os.walk(temp_dir):
                for filename in files:
                    all_files.append(os.path.join(root, filename))

            if all_files:
                for fp in all_files:
                    try:
                        mat2_result = subprocess.run(
                            ['mat2', '--inplace', '--unknown-members', 'omit', fp],
                            capture_output=True, timeout=5
                        )
                        if mat2_result.returncode in (0, 1):
                            cleaned_count += 1
                    except (subprocess.TimeoutExpired, OSError):
                        pass

        output_dir = os.path.dirname(os.path.normpath(paths[0]))
        if len(paths) == 1:
            bundle_name = os.path.basename(os.path.normpath(paths[0]))
        else:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            bundle_name = f"encrypted_bundle_{timestamp}"

        # Create tar.gz in a SEPARATE temp location (not inside temp_dir!)
        tar_fd, tar_path = tempfile.mkstemp(suffix='.tar.gz', prefix='age_archive_')
        os.close(tar_fd)
        result = subprocess.run([
            'tar', '-czf', tar_path, '-C', temp_dir, '.'
        ], capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"tar failed: {stderr}")

        temp_encrypted = os.path.join(temp_dir, f"{bundle_name}.age")
        success = ext.encrypt_file(tar_path, temp_encrypted, passphrase)

        try:
            os.remove(tar_path)
            tar_path = None
        except FileNotFoundError:
            tar_path = None

        encrypted_path = None
        if success:
            encrypted_path = os.path.join(output_dir, f"{bundle_name}.age")
            shutil.move(temp_encrypted, encrypted_path)

        if success and delete_originals:
            for item_path in paths:
                item_path = os.path.normpath(item_path)
                if os.path.isfile(item_path):
                    ext.secure_delete(item_path)
                elif os.path.isdir(item_path):
                    if ext.validate_path(item_path):
                        shutil.rmtree(item_path)

        if success:
            msg = f"✅ {len(paths)} item(s) → {os.path.basename(encrypted_path)} (HSM)"
            if clean_metadata and cleaned_count > 0:
                msg += f" ({cleaned_count} cleaned)"
            if delete_originals:
                msg += " (originals deleted)"
            subprocess.Popen(
                ['notify-send', '-i', 'security-high', 'HSM Encryption Complete', msg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ['notify-send', '-i', 'dialog-error', '-u', 'critical',
                 'HSM Encryption Failed', 'Could not complete encryption.'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Standalone HSM encryption error: {e}")
        subprocess.Popen(
            ['notify-send', '-i', 'dialog-error', '-u', 'critical',
             'HSM Encryption Failed', error_msg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    finally:
        if tar_path:
            try:
                os.remove(tar_path)
            except (FileNotFoundError, OSError):
                pass
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except (FileNotFoundError, OSError):
                pass


# ==============================================================================
# CLI Entry Point
# ==============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AGE Encryption Extension - CLI Mode',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--encrypt', metavar='JSON',
                       help='Encrypt paths (JSON array)')
    parser.add_argument('--decrypt', metavar='JSON',
                       help='Decrypt paths (JSON array)')
    parser.add_argument('--hsm', metavar='JSON',
                       help='HSM encrypt paths (JSON array)')

    args = parser.parse_args()

    if args.encrypt:
        paths = json.loads(args.encrypt)
        standalone_encrypt(paths)
    elif args.decrypt:
        paths = json.loads(args.decrypt)
        standalone_decrypt(paths)
    elif args.hsm:
        paths = json.loads(args.hsm)
        standalone_hsm(paths)
    else:
        # No CLI args - this file was imported as a module (Nautilus extension)
        pass
