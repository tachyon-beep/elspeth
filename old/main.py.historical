import os
import json
import pandas as pd
import logging
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime
import time
import random
import re
from functools import wraps
from openai import AzureOpenAI
# from openpyxl import Workbook  # no direct usage here; Excel in dmp.exporters
import threading
from time import sleep
import yaml
from pathlib import Path
import zipfile
import sys
import requests

# Azure Content Safety for Prompt Shields
# Safety plugins handled via dmp.plugins

# Azure DevOps for archiving
# Azure DevOps archiver moved to dmp.archivers
import base64
import hashlib
import platform

from experiment_runner import ExperimentSuite, ExperimentConfig
try:
    from dmp.stats import StatsAnalyzer  # prefer modular analyzer
except Exception:
    from experiment_stats import StatsAnalyzer  # fallback if package not available

# Ensure local package imports work when running main.py directly
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Refactor Phase 1: import shared helpers from package
from dmp.rate_limit import RateLimiter, initialize_rate_limiter
from dmp.validators import (
    ValidationError,
    validate_text_field,
    validate_context,
    validate_category,
    parse_score,
)
from dmp.costs import CostTracker, estimate_cost
from dmp.checkpoints import ExperimentCheckpoint
from dmp.exporters.excel import save_results_to_excel, create_consolidated_excel
from dmp.io_utils import (
    create_output_zip,
    capture_environment,
    create_data_lineage,
    collect_files_for_archive,
)
from dmp.llm_client import LLMClient
from dmp.core import (
    extract_case_study_data,
    get_all_scores_with_tokens,
)
from dmp.runner import (
    build_context,
    save_experiment_results,
    save_single_experiment_results,
    execute_experiment_suite,
    build_safety_manager,
    build_output_manager,
    emit_outputs,
)
from dmp.plugins import SafetyManager
from dmp.archivers.devops import AzureDevOpsArchiver
from dmp.plugins.output import OutputManager
from dmp.plugins.output_devops import DevOpsOutputPlugin
from dmp.monitoring import AuditLogger, HealthMonitor
from dmp.plugins.prompt_shields import PromptShieldsPlugin

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check if running in Azure ML
try:
    from azureml.core import Run
    azure_run = Run.get_context()
    is_azure_ml = type(azure_run).__name__ != 'InteractiveRun'
except:
    azure_run = None
    is_azure_ml = False

## moved to dmp.exporters.excel.save_results_to_excel

## PromptShieldScreener extracted to dmp.plugins.prompt_shields.PromptShieldsPlugin


## AzureDevOpsArchiver extracted to dmp.archivers.devops.AzureDevOpsArchiver

# Global instances (initialize after rate_limiter)
safety_manager = None
audit_logger = AuditLogger()
devops_archiver = None

def safe_rate_limit():
    if rate_limiter is None:
        raise RuntimeError("Rate limiter not initialized")
    rate_limiter.wait()

# Global rate limiter
rate_limiter = None

class LLMQueryError(Exception):
    """Exception for LLM query errors"""
    pass

def load_configurations(config_path: str = None):
    from dmp.config_loader import load_configurations as _lc
    return _lc(config_path)

def validate_text_field(value: str, field_name: str) -> str:
    from dmp.validators import validate_text_field as _vtf
    return _vtf(value, field_name)

def validate_context(value: str, field_name: str) -> str:
    from dmp.validators import validate_context as _vc
    return _vc(value, field_name)

def validate_category(value: str, field_name: str, category_descriptions: dict) -> str:
    from dmp.validators import validate_category as _vcat
    return _vcat(value, field_name, category_descriptions)

def retry_with_backoff(retries: int = 3, backoff_in_seconds: int = 1):
    """Compatibility wrapper around dmp.llm_client.retry_with_backoff."""
    from dmp.llm_client import retry_with_backoff as _r
    return _r(retries=retries, backoff_in_seconds=backoff_in_seconds)


# Global cost tracker
cost_tracker = CostTracker()

def load_prompts() -> Tuple[str, str]:
    """Load system and user prompts from default prompts/ folder.

    Delegates file IO to dmp.prompts while preserving error types and logging.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        from dmp.prompts import load_prompts_default
        system_prompt, user_prompt = load_prompts_default(script_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        raise LLMQueryError(
            "Prompt file not found at expected location: prompts/system_prompt.md or prompts/user_prompt.md"
        )
    except ValueError as e:
        logger.error(str(e))
        raise LLMQueryError(str(e))
    except Exception as e:
        logger.error(f"Error reading prompts: {str(e)}")
        raise LLMQueryError(f"Failed to read prompts: {str(e)}")

    logger.info(
        f"System prompt preview: {system_prompt[:100].replace(chr(10), ' ')}..."
    )
    logger.info(f"User prompt preview: {user_prompt[:100].replace(chr(10), ' ')}...")
    return system_prompt, user_prompt

def parse_score(response_text: str) -> Tuple[str, str]:
    # Deprecated local definition; kept for backward references during refactor.
    # Use dmp.validators.parse_score instead.
    from dmp.validators import parse_score as _ps
    return _ps(response_text)

def format_user_prompt(
    user_prompt: str,
    cs_data: Dict[str, Any],
    case_study_text: str,
    case_study_summary: str,
    case_study_title: str,
    service_summary: str,
    criteria: str,
    criteria_description: str,
    category_guidance: dict,
) -> str:
    # Delegate to packaged implementation for consistency
    from dmp.prompts import format_user_prompt as _fup
    return _fup(
        user_prompt,
        cs_data,
        case_study_text,
        case_study_summary,
        case_study_title,
        service_summary,
        criteria,
        criteria_description,
        category_guidance,
    )

## moved to dmp.core.extract_case_study_data

## moved to dmp.core.make_single_score_query_with_tokens

## moved to dmp.core.get_all_scores_with_tokens

from dmp.processing import process_data  # use packaged implementation

def query_llm(
    client: AzureOpenAI,
    deployment: str,
    system_prompt: str,
    user_prompt: str,
    input_data: Dict[str, Any],
    config_data: tuple,
    max_tokens: int = 150,
    temperature: float = 0.7,
    experiment_name: str | None = None,
    llm: Optional['LLMClient'] = None,
    cost_tracker: Optional[Any] = None,
) -> Dict[str, Any]:
    """Query LLM for both case studies and return structured result.

    Uses dmp.core.get_all_scores_with_tokens for each case study via the provided
    LLMClient. Keeps the result shape backward-compatible with exporters/stats.
    """
    local_llm = llm or LLMClient(
        client=client,
        deployment=deployment,
        rate_limiter=rate_limiter,
        audit_logger=audit_logger,
    )
    cs1_data = extract_case_study_data(input_data, 1)
    cs2_data = extract_case_study_data(input_data, 2)

    cs1_scores, cs1_raw, cs1_tokens = get_all_scores_with_tokens(
        llm=local_llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cs_data=cs1_data,
        case_study_text=input_data.get("case_study_1", ""),
        case_study_summary=input_data.get("case_study_summary_1", ""),
        case_study_title=input_data.get("case_study_title_1", ""),
        service_summary=input_data.get("service_summary", ""),
        max_tokens=max_tokens,
        temperature=temperature,
        config_data=config_data,
        audit_logger=audit_logger,
    )
    cs2_scores, cs2_raw, cs2_tokens = get_all_scores_with_tokens(
        llm=local_llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cs_data=cs2_data,
        case_study_text=input_data.get("case_study_2", ""),
        case_study_summary=input_data.get("case_study_summary_2", ""),
        case_study_title=input_data.get("case_study_title_2", ""),
        service_summary=input_data.get("service_summary", ""),
        max_tokens=max_tokens,
        temperature=temperature,
        config_data=config_data,
        audit_logger=audit_logger,
    )

    token_usage = {
        "prompt": int(cs1_tokens.get("prompt", 0) + cs2_tokens.get("prompt", 0)),
        "completion": int(cs1_tokens.get("completion", 0) + cs2_tokens.get("completion", 0)),
    }

    return {
        "id": input_data.get("id"),
        "category_name": input_data.get("category_name"),
        "context_1": input_data.get("context_1"),
        "context_2": input_data.get("context_2"),
        "case_study_1_llm": cs1_scores,
        "case_study_2_llm": cs2_scores,
        "case_study_1_rationales": {},
        "case_study_2_rationales": {},
        "case_study_1_raw": cs1_raw,
        "case_study_2_raw": cs2_raw,
        "token_usage": token_usage,
    }

from dmp.heuristics import should_stop_early  # packaged early-stop logic

def run_single_experiment_with_config(
    df: pd.DataFrame, 
    args: argparse.Namespace, 
    client: AzureOpenAI, 
    exp_config: ExperimentConfig,
    exp_rate_limiter: RateLimiter
) -> List[Dict]:
    """Run a single experiment using the shared runner implementation."""
    # Delegate to the runner implementation
    from dmp.runner import execute_single_experiment_with_config as _exec

    return _exec(
        df=df,
        args=args,
        client=client,
        exp_config=exp_config,
        exp_rate_limiter=exp_rate_limiter,
        process_data_fn=process_data,
        query_llm_fn=query_llm,
        should_stop_early_fn=should_stop_early,
        load_configurations_fn=load_configurations,
        azure_run=azure_run,
        is_azure_ml=is_azure_ml,
    )

# save_experiment_results now provided by dmp.runner

def run_single_experiment(df: pd.DataFrame, args: argparse.Namespace) -> Dict:
    """Fallback for single experiment mode using default prompts"""
    logger.info("Running in single experiment mode")
    
    system_prompt, user_prompt = load_prompts()
    config_data = load_configurations()

    client = AzureOpenAI(
        api_key=args.azure_openai_key,
        api_version=args.azure_openai_api_version,
        azure_endpoint=args.azure_openai_endpoint
    )
    
    rate_limiter = initialize_rate_limiter(args.azure_openai_deployment, 1)
    llm = LLMClient(client=client, deployment=args.azure_openai_deployment, rate_limiter=rate_limiter, audit_logger=audit_logger)
    
    successful = []
    failed = []
    
    for idx, row in df.iterrows():
        try:
            processed = process_data(row,config_data)
            
            result = query_llm(
                client=client,
                deployment=args.azure_openai_deployment,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                input_data=processed,
                config_data=config_data, 
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                experiment_name="default",
                llm=llm,
                cost_tracker=cost_tracker,
            )
            
            successful.append(result)
            logger.info(f"✓ Processed ID: {row['APPID']}")
            
        except Exception as e:
            failed.append({
                "id": row.get("APPID", f"row_{idx}"),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            logger.error(f"✗ Failed ID {row.get('APPID')}: {e}")
    
    save_single_experiment_results(successful, failed, args.successful_output, args.failed_output)
    
    return {"default": {"results": successful}}

# save_single_experiment_results now provided by dmp.runner

def run_experiment_suite(df: pd.DataFrame, args: argparse.Namespace) -> Dict:
    """Delegate experiment suite execution to the runner implementation."""
    client = AzureOpenAI(
        api_key=args.azure_openai_key,
        api_version=args.azure_openai_api_version,
        azure_endpoint=args.azure_openai_endpoint,
    )
    # Build context and sync cost tracker with global
    ctx = build_context(
        args=args,
        azure_run=azure_run,
        is_azure_ml=is_azure_ml,
        audit_logger=audit_logger,
        prompt_screener=safety_manager,
        devops_archiver=devops_archiver,
    )
    global cost_tracker
    cost_tracker = ctx.cost_tracker
    # Inject cost_tracker for runner to pass onward to query_llm
    setattr(args, "_cost_tracker", cost_tracker)
    return execute_experiment_suite(
        df,
        args,
        client,
        ctx,
        process_data_fn=process_data,
        query_llm_fn=query_llm,
        should_stop_early_fn=should_stop_early,
        load_configurations_fn=load_configurations,
        run_single_experiment_fn=run_single_experiment,
    )

    

def main():
    # Thin shim: delegate to packaged CLI
    from dmp.cli import main as _cli_main
    _cli_main()

if __name__ == "__main__":
    main()
