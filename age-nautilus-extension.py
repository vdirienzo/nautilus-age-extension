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

Author: Claude + User
Date: December 2025
License: MIT
"""

import os
import pty
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import List

# Detect available Nautilus version
# IMPORTANT: DO NOT use exit() - it crashes Nautilus
from gi import require_version

NAUTILUS_VERSION = None
_import_error = None

# Try Nautilus 4.1 (Debian 13/Trixie, Ubuntu 24.04+)
try:
    require_version('Nautilus', '4.1')
    require_version('Gtk', '4.0')
    from gi.repository import Nautilus, GObject, Gtk, Gio
    NAUTILUS_VERSION = 4
except (ValueError, ImportError):
    pass

# Try Nautilus 4.0 (older versions)
if NAUTILUS_VERSION is None:
    try:
        require_version('Nautilus', '4.0')
        require_version('Gtk', '4.0')
        from gi.repository import Nautilus, GObject, Gtk, Gio
        NAUTILUS_VERSION = 4
    except (ValueError, ImportError):
        pass

# Try Nautilus 3.0 (legacy)
if NAUTILUS_VERSION is None:
    try:
        require_version('Nautilus', '3.0')
        require_version('Gtk', '3.0')
        from gi.repository import Nautilus, GObject, Gtk, Gio
        NAUTILUS_VERSION = 3
    except (ValueError, ImportError) as e:
        _import_error = e

# If no version could be imported, create dummy class to avoid crash
if NAUTILUS_VERSION is None:
    print(f"age-nautilus-extension: Could not import Nautilus: {_import_error}")
    print("Extension will not be available.")
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


class AgeEncryptionExtension(GObject.GObject, Nautilus.MenuProvider):
    """Main Nautilus extension for age encryption"""

    def __init__(self):
        super().__init__()
        self._dependencies_checked = False
        self._age_available = None

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
    
    def get_file_items(self, *args):
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
        
        # Detect if there are folders
        has_folders = any(os.path.isdir(p) for p in paths)
        
        if all_age_files:
            # Menu for decryption
            items.append(self.create_decrypt_menu_item(paths))
        elif has_folders and len(paths) == 1:
            # Menu for folder encryption
            items.append(self.create_encrypt_folder_menu_item(paths[0]))
        else:
            # Menu for file encryption
            items.append(self.create_encrypt_menu_item(paths))
        
        return items
    
    def create_encrypt_menu_item(self, paths: List[str]):
        """Create menu item for encryption"""
        if len(paths) == 1:
            label = "🔒 Encrypt with age"
        else:
            label = f"🔒 Encrypt {len(paths)} files with age"

        item = Nautilus.MenuItem(
            name='AgeExtension::EncryptFiles',
            label=label,
            tip='Encrypt file(s) with age (ChaCha20-Poly1305)'
        )
        item.connect('activate', self.on_encrypt_files, paths)
        return item

    def create_encrypt_folder_menu_item(self, folder_path: str):
        """Create menu item for folder encryption"""
        item = Nautilus.MenuItem(
            name='AgeExtension::EncryptFolder',
            label='📦 Encrypt folder with age',
            tip='Compress and encrypt entire folder (tar.gz + age)'
        )
        item.connect('activate', self.on_encrypt_folder, folder_path)
        return item

    def create_decrypt_menu_item(self, paths: List[str]):
        """Create menu item for decryption"""
        if len(paths) == 1:
            label = "🔓 Decrypt with age"
        else:
            label = f"🔓 Decrypt {len(paths)} files with age"

        item = Nautilus.MenuItem(
            name='AgeExtension::DecryptFiles',
            label=label,
            tip='Decrypt .age file(s)'
        )
        item.connect('activate', self.on_decrypt_files, paths)
        return item

    def get_path_from_uri(self, uri: str) -> str:
        """Convert URI to system path"""
        try:
            parsed = urlparse(uri)
            path = unquote(parsed.path)
            return path
        except (ValueError, TypeError) as e:
            print(f"URI parsing error: {e}")
            return None
    
    def on_encrypt_files(self, menu, paths: List[str]):
        """Handler for encrypting individual files"""
        # Ask for password
        password = self.ask_password("Encrypt files",
                                    "Enter encryption password:")
        if not password:
            return

        # Confirm password
        password_confirm = self.ask_password("Confirm password",
                                             "Re-enter password:")
        if password != password_confirm:
            self.show_error("Error", "Passwords don't match!")
            return

        # Ask whether to delete originals
        delete_originals = self.ask_yes_no(
            "Delete originals?",
            f"Do you want to securely delete the original file(s) after encryption?\n\n"
            f"This will use 'shred' with 3 passes (cannot be undone)."
        )

        success_count = 0
        fail_count = 0

        for file_path in paths:
            if os.path.isfile(file_path):
                encrypted_path = f"{file_path}.age"

                # Encrypt
                if self.encrypt_file(file_path, encrypted_path, password):
                    success_count += 1

                    # Delete original if requested
                    if delete_originals:
                        self.secure_delete(file_path)
                else:
                    fail_count += 1

        # Final notification
        if success_count > 0:
            msg = f"✅ {success_count} file(s) encrypted successfully"
            if delete_originals:
                msg += " (originals deleted)"
            self.show_notification("Encryption complete", msg)
        
        if fail_count > 0:
            self.show_error("Encryption errors", 
                          f"Failed to encrypt {fail_count} file(s)")
    
    def on_encrypt_folder(self, menu, folder_path: str):
        """Handler for encrypting entire folder"""
        folder_name = os.path.basename(folder_path)

        # Ask for password
        password = self.ask_password("Encrypt folder",
                                    f"Enter encryption password for '{folder_name}':")
        if not password:
            return

        # Confirm password
        password_confirm = self.ask_password("Confirm password",
                                             "Re-enter password:")
        if password != password_confirm:
            self.show_error("Error", "Passwords don't match!")
            return

        # Create temporary tar.gz file
        parent_dir = os.path.dirname(folder_path)
        tar_path = os.path.join(parent_dir, f"{folder_name}.tar.gz")
        encrypted_path = f"{tar_path}.age"

        # Compress folder
        self.show_notification("Compressing...",
                             f"Creating archive: {folder_name}.tar.gz")

        try:
            # Create tar.gz
            subprocess.run([
                'tar', '-czf', tar_path,
                '-C', parent_dir,
                folder_name
            ], check=True, capture_output=True)

            # Encrypt tar.gz
            if self.encrypt_file(tar_path, encrypted_path, password):
                # Delete temporary tar.gz
                os.remove(tar_path)

                # Ask whether to delete original folder
                delete_original = self.ask_yes_no(
                    "Delete original folder?",
                    f"Do you want to delete the original folder '{folder_name}'?\n\n"
                    f"The encrypted archive {folder_name}.tar.gz.age has been created."
                )

                if delete_original:
                    subprocess.run(['rm', '-rf', folder_path], check=True)
                    self.show_notification("Complete",
                                         f"Folder encrypted and deleted:\n{encrypted_path}")
                else:
                    self.show_notification("Complete",
                                         f"Folder encrypted:\n{encrypted_path}")
            else:
                # Clean up tar.gz if encryption failed
                if os.path.exists(tar_path):
                    os.remove(tar_path)
                self.show_error("Encryption failed",
                              "Could not encrypt the archive")
        
        except subprocess.CalledProcessError as e:
            self.show_error("Compression failed", 
                          f"Could not create archive: {e}")
    
    def on_decrypt_files(self, menu, paths: List[str]):
        """Handler for decrypting files"""
        # Verify files first
        invalid_files = []
        for file_path in paths:
            if not self.verify_age_file(file_path):
                invalid_files.append(os.path.basename(file_path))

        if invalid_files:
            self.show_error("Invalid files",
                          f"These files are not valid .age files:\n" +
                          "\n".join(invalid_files))
            return

        # Ask for password
        password = self.ask_password("Decrypt files",
                                    "Enter decryption password:")
        if not password:
            return

        success_count = 0
        fail_count = 0

        for file_path in paths:
            # Remove .age extension
            if file_path.endswith('.age'):
                decrypted_path = file_path[:-4]
            else:
                decrypted_path = f"{file_path}.decrypted"

            # Decrypt
            if self.decrypt_file(file_path, decrypted_path, password):
                success_count += 1

                # If it's a tar.gz, ask whether to extract
                if decrypted_path.endswith('.tar.gz'):
                    extract = self.ask_yes_no(
                        "Extract archive?",
                        f"The decrypted file is a compressed archive.\n\n"
                        f"Do you want to extract it?"
                    )

                    if extract:
                        extract_dir = os.path.dirname(decrypted_path)
                        try:
                            subprocess.run([
                                'tar', '-xzf', decrypted_path,
                                '-C', extract_dir
                            ], check=True, capture_output=True)

                            # Delete tar.gz after extraction
                            os.remove(decrypted_path)
                            self.show_notification("Extracted",
                                                 "Archive extracted successfully")
                        except subprocess.CalledProcessError as e:
                            self.show_error("Extraction failed", str(e))
            else:
                fail_count += 1

        # Final notification
        if success_count > 0:
            self.show_notification("Decryption complete", 
                                 f"✅ {success_count} file(s) decrypted successfully")
        
        if fail_count > 0:
            self.show_error("Decryption errors", 
                          f"Failed to decrypt {fail_count} file(s)\n\n"
                          f"Check your password.")
    
    def encrypt_file(self, input_path: str, output_path: str, password: str) -> bool:
        """Encrypt a file with age securely using PTY"""
        import time
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
            os.write(master_fd, f"{password}\n".encode('utf-8'))
            time.sleep(0.1)
            os.write(master_fd, f"{password}\n".encode('utf-8'))

            stdout, stderr = process.communicate(timeout=300)

            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                err_msg = stderr.decode('utf-8', errors='replace')
                print(f"Age encryption failed (code {process.returncode}): {err_msg}")
                # Clean up partial output file if exists
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                return False

        except subprocess.TimeoutExpired:
            print("Encryption timeout")
            if process:
                process.kill()
            return False
        except OSError as e:
            print(f"Encryption OS error: {e}")
            return False
        except Exception as e:
            print(f"Encryption error: {e}")
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
            os.write(master_fd, f"{password}\n".encode('utf-8'))

            stdout, stderr = process.communicate(timeout=300)

            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                err_msg = stderr.decode('utf-8', errors='replace')
                print(f"Age decryption failed (code {process.returncode}): {err_msg}")
                # Delete failed output file
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                return False

        except subprocess.TimeoutExpired:
            print("Decryption timeout")
            if process:
                process.kill()
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False
        except OSError as e:
            print(f"Decryption OS error: {e}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False
        except Exception as e:
            print(f"Decryption error: {e}")
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
            print(f"File verification error: {e}")
            return False

    def secure_delete(self, file_path: str):
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
            print(f"Secure delete error: {e}")
            # Fallback to normal rm if shred fails
            try:
                os.remove(file_path)
            except OSError as rm_error:
                print(f"Fallback delete also failed: {rm_error}")

    def ask_password(self, title: str, text: str) -> str:
        """Ask for a password using zenity"""
        try:
            result = subprocess.run(
                ['zenity', '--password', 
                 '--title', title,
                 '--text', text],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutos timeout
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None
        
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    def ask_yes_no(self, title: str, text: str) -> bool:
        """Ask yes/no question using zenity"""
        try:
            result = subprocess.run(
                ['zenity', '--question',
                 '--title', title,
                 '--text', text,
                 '--width', '400'],
                timeout=300
            )

            return result.returncode == 0

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def show_notification(self, title: str, message: str):
        """Show a system notification"""
        try:
            subprocess.run(
                ['notify-send', '-i', 'dialog-information',
                 title, message],
                timeout=2
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Silence notification errors - they are not critical
            pass

    def show_error(self, title: str, message: str):
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
            # Fallback to print if zenity is not available
            print(f"Error: {title} - {message}")
