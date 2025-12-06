#!/usr/bin/env python3
"""
Downloads encrypted GPG token, decrypts it, and uses it to fetch files from a private GH repo.
"""

import subprocess
import tempfile
import os
import sys
import shutil
import atexit
import signal
import resource
import getpass

# Disable core dumps to prevent creds from being potentially stored
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class TokenManager:
    """Manages secure token lifecycle."""
    
    def __init__(self):
        self.encrypted_token_url = "https://github.com/kmicb/keys/raw/refs/heads/main/gh_token.txt.gpg"
        self.private_repo = "https://raw.githubusercontent.com/kmicb/rpi/main"
        
        # Create temp files with secure permissions (0o600 = rw-------)
        self.tmp_gpg = tempfile.NamedTemporaryFile(delete=False, suffix='.gpg')
        self.tmp_gpg.close()
        os.chmod(self.tmp_gpg.name, 0o600)
        
        self.tmp_token = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        self.tmp_token.close()
        os.chmod(self.tmp_token.name, 0o600)
        
        self.token = None
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle interrupt signals (Ctrl+C, SIGTERM)."""
        self.cleanup()
        sys.exit(1)
    
    def fail(self, message: str):
        """Print error to stderr and exit with status 1."""
        print(f"ERROR: {message}", file=sys.stderr)
        sys.exit(1)
    
    def check_command(self, cmd: str):
        """Verify command exists in PATH."""
        if not shutil.which(cmd):
            self.fail(f"{cmd} not installed")
    
    def secure_rm(self, *files):
        """Securely delete files using shred, with fallback to rm."""
        for filepath in files:
            if not os.path.exists(filepath):
                continue
            
            # Try shred first (Linux/macOS)
            try:
                subprocess.run(
                    ['shred', '-vfz', '-n', '3', filepath],
                    check=True,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                # Fallback to standard rm
                try:
                    os.remove(filepath)
                except OSError:
                    pass
    
    def prompt_passphrase(self) -> str:
        """Prompt user for GPG passphrase securely."""
        try:
            pw = getpass.getpass("Enter GPG passphrase: ")
        except Exception as e:
            self.fail(f"Failed to read passphrase: {e}")
        
        pw = pw.strip()
        if not pw:
            self.fail("Empty passphrase provided")
        return pw
    
    def download_encrypted_token(self):
        """Download encrypted token from GitHub."""
        try:
            subprocess.run(
                ['curl', '-fsSL', self.encrypted_token_url, '-o', self.tmp_gpg.name],
                check=True,
                timeout=30
            )
        except subprocess.CalledProcessError:
            self.fail("Failed to download encrypted token")
        except subprocess.TimeoutExpired:
            self.fail("Download timed out")
    
    def decrypt_token(self, passphrase: str):
        """Decrypt GPG token using passphrase from stdin."""
        process = None
        try:
            process = subprocess.Popen(
                ['gpg', '--quiet', '--batch', '--yes',
                 '--pinentry-mode', 'loopback',
                 '--no-symkey-cache',
                 '--decrypt',
                 '--passphrase-fd', '0',
                 '--output', self.tmp_token.name,
                 self.tmp_gpg.name],
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            process.communicate(input=passphrase.encode(), timeout=10)
            
            if process.returncode != 0:
                self.fail("GPG decryption failed")
        
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            self.fail("GPG decryption timed out")
        except Exception as e:
            self.fail(f"Decryption error: {e}")
    
    def read_token(self) -> str:
        """Read decrypted token from file."""
        try:
            with open(self.tmp_token.name, 'r') as f:
                token = f.read().strip()
            
            if not token:
                self.fail("Decrypted token file is empty")
            
            return token
        
        except IOError as e:
            self.fail(f"Failed to read token file: {e}")
    
    def download_file(self, url: str, output: str):
        """Download file from private GitHub repo using token."""
        try:
            subprocess.run(
                ['curl', '-fsSL',
                 '-H', f'Authorization: token {self.token}',
                 url, '-o', output],
                check=True,
                timeout=30
            )
        except subprocess.CalledProcessError:
            self.fail(f"Failed to download {output}")
        except subprocess.TimeoutExpired:
            self.fail(f"Download of {output} timed out")
    
    def run(self):
        """Execute the full token retrieval and file download workflow."""
        # Check prerequisites
        self.check_command('gpg')
        self.check_command('curl')
        
        # Get passphrase from Keychain
        passphrase = self.prompt_passphrase()
        
        # Download encrypted token
        self.download_encrypted_token()
        
        # Decrypt token
        self.decrypt_token(passphrase)
        
        # Read decrypted token into memory
        self.token = self.read_token()
        
        # Download files
        self.download_file(f"{self.private_repo}/setup_rpi.py", "setup_rpi.py")
        self.download_file(f"{self.private_repo}/config.ini", "config.ini")
        
        print("✓ Successfully downloaded files")
    
    def cleanup(self):
        """Securely clean up sensitive files and variables."""
        self.secure_rm(self.tmp_gpg.name, self.tmp_token.name)
        self.token = None

def main():
    """Main entry point."""
    manager = TokenManager()
    try:
        manager.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        manager.fail(str(e))

if __name__ == "__main__":
    main()