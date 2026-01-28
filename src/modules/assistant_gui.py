import tkinter as tk
from tkinter import ttk
from typing import List

class AssistantGUI:
    def __init__(self, input_devices: List[str] = None, output_devices: List[str] = None):
        self.root = tk.Tk()
        self.root.title("Game Assistant")
        self.root.geometry("600x500")
        
        self.is_muted = False
        
        # Create UI elements
        self._create_widgets()
        self._layout_widgets()
        
    def _create_widgets(self):
        """Create all GUI widgets."""
        # Mute button
        self.mute_btn = tk.Button(
            self.root,
            text="🔊 Unmuted",
            command=self.toggle_mute,
            width=15,
            bg="green",
            fg="white"
        )
        
        # Device selection labels and dropdowns
        tk.Label(self.root, text="Input Device:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.input_device = ttk.Combobox(self.root, values=["Default Mic"], state="readonly")
        self.input_device.current(0)
        
        tk.Label(self.root, text="Output Device:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.output_device = ttk.Combobox(self.root, values=["Default Speaker"], state="readonly")
        self.output_device.current(0)
        
        # Status text box
        tk.Label(self.root, text="Status:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.status_text = tk.Text(self.root, height=2, wrap=tk.WORD, bg="#f0f0f0")
        self.status_text.insert("1.0", "System ready")
        self.status_text.config(state=tk.DISABLED)  # Read-only
        
        # Communication log
        tk.Label(self.root, text="Communication Log:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.comm_text = tk.Text(self.root, height=20, wrap=tk.WORD)
        self.comm_scrollbar = tk.Scrollbar(self.root, command=self.comm_text.yview)
        self.comm_text.config(yscrollcommand=self.comm_scrollbar.set)
        
    def _layout_widgets(self):
        """Layout all widgets using grid."""
        self.mute_btn.grid(row=0, column=0, columnspan=2, pady=10, padx=5)
        
        self.input_device.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.output_device.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        self.status_text.grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        self.comm_text.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.comm_scrollbar.grid(row=6, column=2, sticky="ns", pady=5)
        
        # Make text boxes expandable
        self.root.grid_rowconfigure(6, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
    
    def toggle_mute(self):
        """Toggle mute state."""
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_btn.config(text="🔇 Muted", bg="red")
            self.update_status("Microphone muted")
        else:
            self.mute_btn.config(text="🔊 Unmuted", bg="green")
            self.update_status("Microphone active")
    
    def update_status(self, message: str):
        """Update the status text box."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", message)
        self.status_text.config(state=tk.DISABLED)
    
    def add_message(self, role: str, message: str):
        """Add a message to the communication log."""
        self.comm_text.insert(tk.END, f"{role}: {message}\n\n")
        self.comm_text.see(tk.END)  # Auto-scroll to bottom

    def add_message_stream(self, message_chunk: str):
        """Add a chunk of message to the communication log (for streaming)."""
        self.comm_text.insert(tk.END, message_chunk)
        self.comm_text.see(tk.END)  # Auto-scroll to bottom
    
    def get_input_device(self) -> str:
        """Get selected input device."""
        return self.input_device.get()
    
    def get_output_device(self) -> str:
        """Get selected output device."""
        return self.output_device.get()
    
    def run(self):
        """Start the GUI event loop."""
        self.root.mainloop()


# Example usage
if __name__ == "__main__":
    gui = AssistantGUI()
    
    # Example: Add some test messages
    gui.add_message("User", "How do I craft bread?")
    gui.add_message("Assistant", "To craft bread, you need 3 wheat in a horizontal row.")
    
    gui.run()