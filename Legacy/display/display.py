import tkinter as tk
from tkinter import ttk
import math
import random

class ScrollableFrame(ttk.Frame):
    """A scrollable frame that works with mouse wheel/trackpad"""
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Configure canvas scrolling
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        # Create window in canvas for the frame
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack elements
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Bind mouse wheel/trackpad events
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)  # Linux
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)  # Linux
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        
    def _on_mousewheel(self, event):
        """Handle mouse wheel/trackpad scrolling"""
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
    
    def _bind_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

def generate_pi_sequence(start_digits, count):
    """Generate pi values with increasing digits"""
    return [f"{math.pi:.{i}f}" for i in range(start_digits, start_digits + count)]

def get_random_color():
    """Return either 'green' or 'red' randomly"""
    return random.choice(['green', 'red'])

def create_app():
    # Create main window
    root = tk.Tk()
    root.title("Pi Display App")
    root.geometry("1400x1000")  # Larger window to accommodate bigger font
    
    # Make it feel more native on Mac
    root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w, "document", "closeBox")
    
    # Configure grid layout to be resizable
    for i in range(2):
        root.grid_rowconfigure(i, weight=1)
    for i in range(3):
        root.grid_columnconfigure(i, weight=1, uniform="columns")
    
    # Box titles configuration
    box_titles = {
        0: "New PF Tokens (pumpScrape13.py)",      # Top left
        1: "Tracked Window (jupSimple9-500.py)", # Top middle
        2: "Current Buys (whenBuy.py/sellAlg.py)",       # Top right
        3: "All Trades (SolScanGet.py (red, green and yellow for +20%))",         # Bottom right
        4: "Winning Trades(filterSolScan.py)",     # Bottom middle
        5: "Stats (SolScanStats.py)"               # Bottom left
    }
    
    # Create frames (boxes) in a 2x3 grid
    frames = []
    for row in range(2):
        for col in range(3):
            # Calculate box index (0-5)
            box_idx = row * 3 + col
            
            # Create outer container frame
            outer_frame = ttk.Frame(root, borderwidth=2, relief="groove", padding=5)
            outer_frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            outer_frame.grid_propagate(False)
            
            # Add title label at the top
            title_frame = ttk.Frame(outer_frame)
            title_frame.pack(fill="x", pady=(0, 5))
            
            title_label = ttk.Label(title_frame, text=box_titles[box_idx], 
                                  font=('Helvetica', 14, 'bold'))
            title_label.pack(side="left")
            
            # Special case: Add dollar amount to Stats box
            if box_idx == 5:  # Stats box
                dollar_label = ttk.Label(title_frame, text="$21,125.23", 
                                       font=('Helvetica', 32, 'bold'),
                                       foreground="green")
                dollar_label.pack(side="right")
            
            # Create scrollable area
            scrollable_frame = ScrollableFrame(outer_frame)
            scrollable_frame.pack(fill="both", expand=True)
            
            # Store references to all frames
            frames.append((outer_frame, scrollable_frame.scrollable_frame, box_idx))
    
    # Add content to each box
    for frame_info in frames:
        outer_frame, scroll_frame, box_idx = frame_info
        
        if box_idx == 5:  # Stats box (special layout)
            # Add stats content at the bottom
            stats_frame = ttk.Frame(scroll_frame)
            stats_frame.pack(side="bottom", fill="x", expand=True, pady=20)
            
            stats = [
                "Lives (4/4)",
                "Smash outs (5/5)",
                "Attempts (50/50)",
                "Daily Achievement hit (0/10)"
            ]
            
            for stat in stats:
                lbl = ttk.Label(stats_frame, text=stat, font=('Helvetica', 14))
                lbl.pack(anchor='w', pady=10)
        else:
            # Add pi sequences to other boxes (40 rows each)
            for j, pi_value in enumerate(generate_pi_sequence(3, 40)):
                # All numbers in Winning Trades box (index 4) are green
                if box_idx == 4:  # Winning Trades box
                    color = 'green'
                else:
                    color = get_random_color()
                    
                lbl = ttk.Label(scroll_frame, text=pi_value, font=('Menlo', 14),
                              anchor='w', foreground=color)
                lbl.pack(fill='x', pady=1)
    
    # Make window resizable with minimum size
    root.minsize(1000, 800)
    root.resizable(True, True)

    root.mainloop()

if __name__ == "__main__":
    create_app()