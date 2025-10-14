from datetime import datetime
import hashlib
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional,TypedDict
import yaml
import tempfile
import jsonschema

logger = logging.getLogger(__name__)

class ExperimentConfigSchema(TypedDict):
    name: str
    description: str
    temperature: float
    max_tokens: int
    enabled: bool
    is_baseline: bool
    
CONFIG_SCHEMA = {
    "type": "object",
    "required": ["name", "temperature", "max_tokens", "enabled"],
    "properties": {
        "name": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
        "enabled": {"type": "boolean"},
        "is_baseline": {"type": "boolean"}
    }
}

def validate_config(config: dict) -> None:
    """Validate configuration against schema"""
    jsonschema.validate(config, CONFIG_SCHEMA)

class ExperimentConfig:
    """Represents a single experiment configuration with validation"""
    
    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        
        # Load config.json
        config_path = os.path.join(folder_path, "config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Validate config against schema
        try:
            validate_config(self.config)  # Now actually use the validation
        except jsonschema.ValidationError as e:
            raise ValueError(f"Config validation failed: {str(e)}")

        # Load experiment-specific configurations if available
        self.configurations_path = os.path.join(folder_path, "configurations.yaml")
        self.has_custom_configurations = os.path.exists(self.configurations_path)

        # Load prompts
        system_prompt_path = os.path.join(folder_path, "system_prompt.md")
        user_prompt_path = os.path.join(folder_path, "user_prompt.md")
        
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()
            
        with open(user_prompt_path, 'r', encoding='utf-8') as f:
            self.user_prompt = f.read()
        
        # Validate on load
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid experiment config: {', '.join(errors)}")
    
    @property
    def name(self) -> str:
        return self.config.get("name", self.folder_name)
    
    @property
    def description(self) -> str:
        return self.config.get("description", "")
    
    @property
    def hypothesis(self) -> str:
        return self.config.get("hypothesis", "")
    
    @property
    def author(self) -> str:
        return self.config.get("author", "unknown")
    
    @property
    def temperature(self) -> float:
        return self.config.get("temperature", 0.0)
    
    @property
    def max_tokens(self) -> int:
        return self.config.get("max_tokens", 300)
    
    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)
    
    @property
    def is_baseline(self) -> bool:
        return self.config.get("is_baseline", False)
    
    @property
    def tags(self) -> List[str]:
        return self.config.get("tags", [])
    
    @property
    def expected_outcome(self) -> str:
        return self.config.get("expected_outcome", "")
    
    @property
    def estimated_cost(self) -> Dict[str, float]:
        """Estimate cost for this experiment configuration"""
        # Rough estimates - adjust based on your model
        cost_per_1k_tokens = {
            "input": 0.03,   # GPT-4 pricing
            "output": 0.06
        }
        
        # Estimate tokens per request
        avg_input_tokens = 2000  # Rough estimate for prompts
        avg_output_tokens = self.max_tokens
        
        # Assuming 100 rows, 2 case studies, 5 criteria each
        total_requests = 100 * 2 * 5
        
        total_input_tokens = total_requests * avg_input_tokens
        total_output_tokens = total_requests * avg_output_tokens
        
        input_cost = (total_input_tokens / 1000) * cost_per_1k_tokens["input"]
        output_cost = (total_output_tokens / 1000) * cost_per_1k_tokens["output"]
        
        return {
            "estimated_input_cost": input_cost,
            "estimated_output_cost": output_cost,
            "estimated_total_cost": input_cost + output_cost,
            "estimated_requests": total_requests
        }
    
    def validate(self) -> List[str]:
        """Validate experiment configuration"""
        errors = []
        
        # Check required files exist
        required_files = ["config.json", "system_prompt.md", "user_prompt.md"]
        for file in required_files:
            file_path = os.path.join(self.folder_path, file)
            if not os.path.exists(file_path):
                errors.append(f"Missing {file}")
            elif os.path.getsize(file_path) == 0:
                errors.append(f"Empty {file}")
        
        # Validate config values
        if not (0 <= self.temperature <= 2):
            errors.append(f"Invalid temperature: {self.temperature} (must be 0-2)")
            
        if not (1 <= self.max_tokens <= 8192):
            errors.append(f"Invalid max_tokens: {self.max_tokens} (must be 1-8192)")
        
        # Validate prompts not empty
        if hasattr(self, 'system_prompt') and not self.system_prompt.strip():
            errors.append("System prompt is empty")
            
        if hasattr(self, 'user_prompt') and not self.user_prompt.strip():
            errors.append("User prompt is empty")
        
        return errors
    
    @staticmethod
    def stable_hash(text: str) -> str:
        """Create stable hash for text comparison"""
        return hashlib.md5(text.encode()).hexdigest()[:8]
    
    def differs_from(self, other: 'ExperimentConfig') -> Dict[str, Any]:
        """Compare this experiment with another to identify differences"""
        differences = {}
        
        # Compare config values
        for key in ['temperature', 'max_tokens']:
            if getattr(self, key) != getattr(other, key):
                differences[key] = {
                    'this': getattr(self, key),
                    'other': getattr(other, key)
                }
        
        # Compare prompts (just length/hash for summary)
        if self.system_prompt != other.system_prompt:
            differences['system_prompt'] = {
                'this_length': len(self.system_prompt),
                'other_length': len(other.system_prompt),
                'this_hash': self.stable_hash(self.system_prompt),
                'other_hash': self.stable_hash(other.system_prompt)
            }
            
        if self.user_prompt != other.user_prompt:
            differences['user_prompt'] = {
                'this_length': len(self.user_prompt),
                'other_length': len(other.user_prompt),
                'this_hash': self.stable_hash(self.user_prompt),
                'other_hash': self.stable_hash(other.user_prompt)
            }
            
        return differences
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for serialization"""
        return {
            "name": self.name,
            "folder_name": self.folder_name,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "author": self.author,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
            "is_baseline": self.is_baseline,
            "tags": self.tags,
            "expected_outcome": self.expected_outcome,
            "estimated_cost": self.estimated_cost
        }


from dmp.checkpoints import ExperimentCheckpoint


class ExperimentSuite:
    """Manages multiple experiments with Azure ML integration"""
    
    def __init__(self, experiments_root: str, azure_run=None):
        self.experiments_root = experiments_root
        self.azure_run = azure_run
        self.is_azure_ml = azure_run is not None and type(azure_run).__name__ != 'InteractiveRun'
        self.experiments = self._discover_experiments()
        
        # Log to Azure ML if available
        if self.is_azure_ml:
            self.azure_run.log("experiment_count", len(self.experiments))
            for exp in self.experiments:
                self.azure_run.log_row(
                    "experiments",
                    experiment_name=exp.name,  # ← Changed from 'name' to 'experiment_name'
                    temperature=exp.temperature,
                    max_tokens=exp.max_tokens,
                    is_baseline=exp.is_baseline
                )
    
    def _discover_experiments(self) -> List[ExperimentConfig]:
        """Find and load all valid experiments"""
        experiments = []
        
        if not os.path.exists(self.experiments_root):
            logger.warning(f"Experiments root does not exist: {self.experiments_root}")
            return experiments
        
        # Get sorted list of experiment folders
        exp_folders = sorted([
            d for d in os.listdir(self.experiments_root)
            if os.path.isdir(os.path.join(self.experiments_root, d))
            and not d.startswith('.')  # Skip hidden folders
        ])
        
        for folder in exp_folders:
            folder_path = os.path.join(self.experiments_root, folder)
            try:
                exp = ExperimentConfig(folder_path)
                if exp.enabled:
                    experiments.append(exp)
                    logger.info(f"✓ Loaded experiment: {exp.name} "
                               f"(temp={exp.temperature}, tokens={exp.max_tokens})")
                else:
                    logger.info(f"⊘ Skipped disabled experiment: {folder}")
            except Exception as e:
                logger.warning(f"✗ Failed to load experiment from {folder}: {e}")
        
        # Identify baseline
        baseline_count = sum(1 for exp in experiments if exp.is_baseline)
        if baseline_count == 0:
            logger.warning("No baseline experiment identified")
        elif baseline_count > 1:
            logger.warning(f"Multiple baseline experiments found ({baseline_count})")

        if baseline_count > 1:
            # Pick first baseline found and disable others
            found_baseline = False
            for exp in experiments:
                if exp.is_baseline:
                    if not found_baseline:
                        found_baseline = True
                        logger.warning(f"Using {exp.name} as baseline")
                    else:
                        exp.config["is_baseline"] = False  # Disable other baselines
                        logger.warning(f"Disabled baseline flag for {exp.name}")

        return experiments
    
    def get_baseline(self) -> Optional[ExperimentConfig]:
        """Get the baseline experiment"""
        for exp in self.experiments:
            if exp.is_baseline:
                return exp
        
        # Default to first experiment if no explicit baseline
        if self.experiments:
            logger.info(f"No explicit baseline, using {self.experiments[0].name}")
            return self.experiments[0]
        
        return None
    
    def preflight_check(self, row_count: int = 100) -> Dict[str, Any]:
        """Run pre-flight validation before executing experiments"""
        issues = []
        warnings = []
        
        # Check for baseline
        baseline = self.get_baseline()
        if not baseline:
            issues.append("No baseline experiment found")
        
        # Check for duplicate names
        names = [exp.name for exp in self.experiments]
        if len(names) != len(set(names)):
            issues.append("Duplicate experiment names found")
        
        # Estimate total API calls and time
        estimated_calls = len(self.experiments) * row_count * 5 * 2  # experiments * rows * criteria * case studies
        estimated_time_min = estimated_calls / 60  # Rough estimate
        
        # Check for very high temperatures
        high_temp_exps = [exp.name for exp in self.experiments if exp.temperature > 1.5]
        if high_temp_exps:
            warnings.append(f"High temperature (>1.5) experiments: {', '.join(high_temp_exps)}")
        
        # Check for very high token counts
        high_token_exps = [exp.name for exp in self.experiments if exp.max_tokens > 2000]
        if high_token_exps:
            warnings.append(f"High token count (>2000) experiments: {', '.join(high_token_exps)}")
        
        # Calculate total estimated cost
        total_cost = sum(exp.estimated_cost['estimated_total_cost'] for exp in self.experiments)
        
        return {
            "ready": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "experiment_count": len(self.experiments),
            "estimated_api_calls": estimated_calls,
            "estimated_time_minutes": estimated_time_min,
            "estimated_total_cost": total_cost,
            "baseline": baseline.name if baseline else None,
            "experiments": [exp.name for exp in self.experiments]
        }
    
    def get_execution_order(self) -> List[ExperimentConfig]:
        """Determine optimal execution order for experiments"""
        ordered = []
        
        # Always run baseline first
        baseline = self.get_baseline()
        if baseline:
            ordered.append(baseline)
        
        # Then run experiments by priority (lower tokens/temp first to fail fast)
        remaining = [exp for exp in self.experiments if exp != baseline]
        remaining.sort(key=lambda x: (x.max_tokens, x.temperature))
        
        ordered.extend(remaining)
        return ordered
    
    def log_metrics(self, exp_name: str, metrics: Dict[str, Any]):
        """Log metrics to Azure ML if available"""
        if self.is_azure_ml:
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    self.azure_run.log(f"{exp_name}_{key}", value)
    
    def log_experiment_comparison(self, baseline: ExperimentConfig, 
                                 variant: ExperimentConfig):
        """Log experiment differences to Azure ML"""
        if not self.is_azure_ml:
            return
            
        differences = variant.differs_from(baseline)
        
        # Log as table in Azure ML
        self.azure_run.log_table(
            f"config_diff_{variant.name}",
            differences
        )
        
        # Log key metrics
        for key, diff in differences.items():
            if isinstance(diff, dict) and 'this' in diff:
                if isinstance(diff['this'], (int, float)) and isinstance(diff['other'], (int, float)):
                    self.azure_run.log(
                        f"{variant.name}_diff_{key}",
                        diff['this'] - diff['other']
                    )
                else:
                    self.azure_run.log(
                        f"{variant.name}_diff_{key}",
                        str(diff)
                    )
    
    def export_configuration(self, output_file: str):
        """Export all experiment configurations to a single file"""
        export_data = {
            "suite_metadata": {
                "experiment_count": len(self.experiments),
                "baseline": self.get_baseline().name if self.get_baseline() else None,
                "exported_at": datetime.now().isoformat()
            },
            "experiments": [exp.to_dict() for exp in self.experiments]
        }
        
        if output_file.endswith('.yaml'):
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(export_data, f, default_flow_style=False)
        else:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported {len(self.experiments)} experiments to {output_file}")
    
    def create_experiment_template(self, 
                                  name: str, 
                                  base_experiment: Optional[str] = None) -> str:
        """Create a new experiment from template"""
        new_folder = os.path.join(self.experiments_root, name)
        
        if os.path.exists(new_folder):
            raise ValueError(f"Experiment {name} already exists")
        
        os.makedirs(new_folder)
        
        # Use base experiment or baseline as template
        if base_experiment:
            base_path = os.path.join(self.experiments_root, base_experiment)
        else:
            baseline = self.get_baseline()
            base_path = baseline.folder_path if baseline else None
        
        if base_path and os.path.exists(base_path):
            # Copy prompts from base
            import shutil
            for file in ["system_prompt.md", "user_prompt.md"]:
                src = os.path.join(base_path, file)
                dst = os.path.join(new_folder, file)
                if os.path.exists(src):
                    shutil.copy(src, dst)
            
            # Copy and modify config
            src_config = os.path.join(base_path, "config.json")
            if os.path.exists(src_config):
                with open(src_config, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                config["name"] = name
                config["is_baseline"] = False
                config["enabled"] = False  # Disabled by default for safety
                config["created_date"] = datetime.now().isoformat()
        else:
            # Create default templates
            config = {
                "name": name,
                "description": "New experiment",
                "hypothesis": "To be defined",
                "author": "unknown",
                "created_date": datetime.now().isoformat(),
                "tags": [],
                "expected_outcome": "To be defined",
                "temperature": 0.0,
                "max_tokens": 300,
                "enabled": False,
                "is_baseline": False
            }
            
            # Create empty prompt files
            with open(os.path.join(new_folder, "system_prompt.md"), 'w', encoding='utf-8') as f:
                f.write("# System Prompt\n\nDefine the system prompt here.")
            
            with open(os.path.join(new_folder, "user_prompt.md"), 'w', encoding='utf-8') as f:
                f.write("# User Prompt\n\nDefine the user prompt here.")
        
        # Save config
        with open(os.path.join(new_folder, "config.json"), 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Created experiment template: {new_folder}")
        return new_folder
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all experiments"""
        baseline = self.get_baseline()
        
        return {
            "total_experiments": len(self.experiments),
            "baseline": baseline.name if baseline else None,
            "experiments": [
                {
                    "name": exp.name,
                    "temperature": exp.temperature,
                    "max_tokens": exp.max_tokens,
                    "is_baseline": exp.is_baseline,
                    "tags": exp.tags,
                    "estimated_cost": exp.estimated_cost['estimated_total_cost']
                }
                for exp in self.experiments
            ],
            "total_estimated_cost": sum(
                exp.estimated_cost['estimated_total_cost'] 
                for exp in self.experiments
            )
        }
