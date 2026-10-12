from shared.contracts.schemas import PermissionLevel

def classify_risk(action_name: str) -> PermissionLevel:
    """Classifies risk level based on the name of the operation/action requested."""
    action_lower = action_name.lower()
    
    # HIGH RISK: System execution, scripting, deleting files, database purging, etc.
    high_risk_keywords = ["execute", "run_script", "delete", "destroy", "purge", "rm", "sudo", "write_system"]
    if any(k in action_lower for k in high_risk_keywords):
        return PermissionLevel.HIGH
        
    # MEDIUM RISK: Active web browsing, file writes, reading document content, downloading files
    medium_risk_keywords = ["browse", "scrape", "visit", "download", "write_file", "save_document", "read_file"]
    if any(k in action_lower for k in medium_risk_keywords):
        return PermissionLevel.MEDIUM
        
    # LOW RISK: Text-to-speech, speech transcriptions, DB reading, liveness queries, configuration loading
    return PermissionLevel.LOW

def requires_confirmation(action_name: str, level: PermissionLevel) -> bool:
    """Determines whether the task requires manual user confirmation before running."""
    # HIGH risk commands require explicit user consent
    if level == PermissionLevel.HIGH:
        return True
    return False

def request_user_confirmation(action: str, level: PermissionLevel) -> bool:
    """Placeholder authorization guard that checks permissions before executing tasks.
    
    In future phases, this will trigger websocket events to the dashboard asking for user click-consent.
    """
    # TODO: Connect with desktop UI socket event channels to prompt User interface popups.
    if level == PermissionLevel.HIGH:
        # Default to false (block execution) for high-risk until manual confirmation mechanism is built
        print(f"[SECURITY] [BLOCKED] Action '{action}' classified as HIGH risk. Blocked by default in skeleton phase.")
        return False
    elif level == PermissionLevel.MEDIUM:
        # Warn but allow in skeleton phase
        print(f"[SECURITY] [WARNING] Action '{action}' classified as MEDIUM risk. Proceeding with execution.")
        return True
        
    # Low risk is silently allowed
    return True
