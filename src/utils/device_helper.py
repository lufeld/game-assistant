"""Helper functions for managing audio input/output devices."""

from typing import List, Tuple
import sounddevice as sd

def list_host_apis() -> List[Tuple[int, str]]:
    """List available host APIs for audio devices.
    
    Returns:
        List of tuples (host_api_index, host_api_name)
    """
    host_apis = sd.query_hostapis()
    return [(i, api['name']) for i, api in enumerate(host_apis)]


def list_input_devices(host_api: int = 0) -> List[Tuple[int, str]]:
    """List available input audio devices.
    
    Args:
        host_api: If provided, filters devices by this host API index.
        
    Returns:
        List of tuples (device_index, device_name) where device_index is the ID 
        to pass to sounddevice functions
    """
    devices = sd.query_devices()
    input_devices = []
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            name = device['name']
            
            # Filter for host API if specified
            if host_api is not None and device['hostapi'] != host_api:
                continue
            
            input_devices.append((i, name))
    
    return input_devices


def list_output_devices(host_api: int = 0) -> List[Tuple[int, str]]:
    """List available output audio devices.
    
    Args:
        host_api: If provided, filters devices by this host API index.
        
    Returns:
        List of tuples (device_index, device_name) where device_index is the ID 
        to pass to sounddevice or pyttsx3 functions
    """
    devices = sd.query_devices()
    output_devices = []
    
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            name = device['name']
            
            # Filter for host API if specified
            if host_api is not None and device['hostapi'] != host_api:
                continue
            
            output_devices.append((i, name))
    
    return output_devices


def get_default_input_device() -> Tuple[int, str]:
    """Get the default input device.
    
    Returns:
        Tuple of (device_index, device_name) for the system default input device
    """
    default_device = sd.query_devices(kind='input')
    device_index = default_device['index']
    return (device_index, default_device['name'])


def get_default_output_device() -> Tuple[int, str]:
    """Get the default output device.
    
    Returns:
        Tuple of (device_index, device_name) for the system default output device
    """
    default_device = sd.query_devices(kind='output')
    device_index = default_device['index']
    return (device_index, default_device['name'])


def format_device_list_for_gui(devices: List[Tuple[int, str]]) -> List[str]:
    """Format device list for GUI dropdown display.
    
    Args:
        devices: List of (index, name) tuples from list_input_devices or list_output_devices
        
    Returns:
        List of strings formatted as "[index] Device Name" for display
    """
    return [f"[{idx}] {name}" for idx, name in devices]


def parse_device_selection(selection: str) -> int:
    """Extract device index from GUI selection string.
    
    Args:
        selection: String in format "[index] Device Name"
        
    Returns:
        Device index as integer
    """
    if not selection or '[' not in selection:
        return None
    return int(selection.split(']')[0].strip('['))


# Example usage and testing
if __name__ == "__main__":
    print("=== INPUT DEVICES ===")
    input_devs = list_input_devices()
    for idx, name in input_devs:
        print(f"  [{idx}] {name}")
    
    print("\n=== OUTPUT DEVICES ===")
    output_devs = list_output_devices()
    for idx, name in output_devs:
        print(f"  [{idx}] {name}")
    
    print("\n=== DEFAULT DEVICES ===")
    default_in = get_default_input_device()
    print(f"Default Input:  [{default_in[0]}] {default_in[1]}")
    
    default_out = get_default_output_device()
    print(f"Default Output: [{default_out[0]}] {default_out[1]}")
    
    print("\n=== GUI FORMAT ===")
    gui_list = format_device_list_for_gui(input_devs[:3])
    for item in gui_list:
        print(f"  {item}")
    
    print("\n=== PARSE SELECTION ===")
    test_selection = "[3] Microphone (High Definition Audio Device)"
    parsed_idx = parse_device_selection(test_selection)
    print(f"Selection: {test_selection}")
    print(f"Parsed Index: {parsed_idx}")
