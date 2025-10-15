#!/usr/bin/env python3
"""
N8N-style Workflow-based MTA Filter
This module provides a workflow-based email filtering system similar to n8n workflows.
"""

import json
import sys
import os
import re
import email
import logging
from typing import Dict, List, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/mail/n8n-mta-filter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('n8n-mta-filter')

class WorkflowNode:
    """Base class for workflow nodes"""
    
    def __init__(self, node_id: str, node_type: str, config: Dict[str, Any]):
        self.node_id = node_id
        self.node_type = node_type
        self.config = config
        self.connections = []
    
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the node logic"""
        raise NotImplementedError("Subclasses must implement execute method")
    
    def add_connection(self, target_node: str, condition: Optional[str] = None):
        """Add connection to another node"""
        self.connections.append({
            'target': target_node,
            'condition': condition
        })

class TriggerNode(WorkflowNode):
    """Email trigger node - entry point for email processing"""
    
    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, 'trigger', config)
    
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming email data"""
        logger.info(f"Email trigger activated: {data.get('subject', 'No Subject')}")
        return data

class FilterNode(WorkflowNode):
    """Filter node for conditional email processing"""
    
    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, 'filter', config)
        self.conditions = config.get('conditions', [])
    
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply filter conditions"""
        result = data.copy()
        result['filter_results'] = []
        
        for condition in self.conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            field_value = self._get_field_value(data, field)
            match_result = self._evaluate_condition(field_value, operator, value)
            
            result['filter_results'].append({
                'field': field,
                'operator': operator,
                'value': value,
                'result': match_result
            })
            
            logger.info(f"Filter condition: {field} {operator} {value} = {match_result}")
        
        # Determine overall filter result
        logic = self.config.get('logic', 'AND')
        if logic == 'AND':
            result['filter_passed'] = all(r['result'] for r in result['filter_results'])
        else:  # OR
            result['filter_passed'] = any(r['result'] for r in result['filter_results'])
        
        return result
    
    def _get_field_value(self, data: Dict[str, Any], field: str) -> str:
        """Extract field value from email data"""
        field_map = {
            'sender': 'from',
            'recipient': 'to',
            'subject': 'subject',
            'body': 'body',
            'size': 'size'
        }
        
        actual_field = field_map.get(field, field)
        return str(data.get(actual_field, ''))
    
    def _evaluate_condition(self, field_value: str, operator: str, value: str) -> bool:
        """Evaluate a single condition"""
        try:
            if operator == 'equals':
                return field_value.lower() == value.lower()
            elif operator == 'contains':
                return value.lower() in field_value.lower()
            elif operator == 'starts_with':
                return field_value.lower().startswith(value.lower())
            elif operator == 'ends_with':
                return field_value.lower().endswith(value.lower())
            elif operator == 'regex':
                return bool(re.search(value, field_value, re.IGNORECASE))
            elif operator == 'not_equals':
                return field_value.lower() != value.lower()
            elif operator == 'not_contains':
                return value.lower() not in field_value.lower()
            elif operator == 'greater_than':
                return float(field_value) > float(value)
            elif operator == 'less_than':
                return float(field_value) < float(value)
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False

class ActionNode(WorkflowNode):
    """Action node for email processing actions"""
    
    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, 'action', config)
        self.action_type = config.get('action_type')
    
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the action"""
        result = data.copy()
        
        if self.action_type == 'reject':
            result['action'] = 'reject'
            result['reject_reason'] = self.config.get('reason', 'Message rejected by filter')
            logger.info(f"Email rejected: {result['reject_reason']}")
        
        elif self.action_type == 'quarantine':
            result['action'] = 'quarantine'
            result['quarantine_folder'] = self.config.get('folder', '/var/mail/quarantine')
            logger.info("Email quarantined")
        
        elif self.action_type == 'forward':
            result['action'] = 'forward'
            result['forward_to'] = self.config.get('forward_to')
            logger.info(f"Email forwarded to: {result['forward_to']}")
        
        elif self.action_type == 'modify_headers':
            result['action'] = 'modify_headers'
            result['header_modifications'] = self.config.get('headers', {})
            logger.info("Email headers modified")
        
        elif self.action_type == 'accept':
            result['action'] = 'accept'
            logger.info("Email accepted")
        
        elif self.action_type == 'tag':
            result['action'] = 'tag'
            result['tags'] = self.config.get('tags', [])
            logger.info(f"Email tagged: {result['tags']}")
        
        return result

class WorkflowEngine:
    """N8N-style workflow execution engine"""
    
    def __init__(self, workflow_config: Dict[str, Any]):
        self.workflow_config = workflow_config
        self.nodes = {}
        self.connections = {}
        self._build_workflow()
    
    def _build_workflow(self):
        """Build workflow from configuration"""
        nodes_config = self.workflow_config.get('nodes', [])
        
        for node_config in nodes_config:
            node_id = node_config['id']
            node_type = node_config['type']
            
            if node_type == 'trigger':
                node = TriggerNode(node_id, node_config)
            elif node_type == 'filter':
                node = FilterNode(node_id, node_config)
            elif node_type == 'action':
                node = ActionNode(node_id, node_config)
            else:
                logger.warning(f"Unknown node type: {node_type}")
                continue
            
            self.nodes[node_id] = node
        
        # Build connections
        connections_config = self.workflow_config.get('connections', [])
        for conn in connections_config:
            source = conn['source']
            target = conn['target']
            condition = conn.get('condition')
            
            if source in self.nodes:
                self.nodes[source].add_connection(target, condition)
    
    def execute(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute workflow with email data"""
        logger.info("Starting workflow execution")
        
        # Find trigger node
        trigger_node = None
        for node in self.nodes.values():
            if node.node_type == 'trigger':
                trigger_node = node
                break
        
        if not trigger_node:
            logger.error("No trigger node found in workflow")
            return {'action': 'accept', 'error': 'No trigger node'}
        
        # Execute workflow
        current_data = email_data.copy()
        visited_nodes = set()
        
        return self._execute_node(trigger_node, current_data, visited_nodes)
    
    def _execute_node(self, node: WorkflowNode, data: Dict[str, Any], visited: set) -> Dict[str, Any]:
        """Execute a single node and follow connections"""
        if node.node_id in visited:
            logger.warning(f"Circular reference detected at node: {node.node_id}")
            return data
        
        visited.add(node.node_id)
        
        # Execute current node
        result = node.execute(data)
        
        # Follow connections
        for connection in node.connections:
            target_id = connection['target']
            condition = connection['condition']
            
            # Check if connection condition is met
            if self._should_follow_connection(result, condition):
                if target_id in self.nodes:
                    target_node = self.nodes[target_id]
                    result = self._execute_node(target_node, result, visited.copy())
                else:
                    logger.warning(f"Target node not found: {target_id}")
        
        return result
    
    def _should_follow_connection(self, data: Dict[str, Any], condition: Optional[str]) -> bool:
        """Determine if connection should be followed"""
        if not condition:
            return True
        
        if condition == 'true' and data.get('filter_passed'):
            return True
        elif condition == 'false' and not data.get('filter_passed'):
            return True
        
        return False

class EmailProcessor:
    """Main email processing class"""
    
    def __init__(self, config_file: str = '/etc/postfix/n8n-workflow.json'):
        self.config_file = config_file
        self.workflow_engine = None
        self._load_config()
    
    def _load_config(self):
        """Load workflow configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                self.workflow_engine = WorkflowEngine(config)
                logger.info("Workflow configuration loaded successfully")
            else:
                logger.warning(f"Config file not found: {self.config_file}")
                self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default workflow configuration"""
        default_config = {
            "name": "Default Email Filter Workflow",
            "description": "Basic spam and security filtering",
            "nodes": [
                {
                    "id": "trigger1",
                    "type": "trigger",
                    "name": "Email Received"
                },
                {
                    "id": "filter1",
                    "type": "filter",
                    "name": "Spam Filter",
                    "logic": "OR",
                    "conditions": [
                        {
                            "field": "subject",
                            "operator": "contains",
                            "value": "[SPAM]"
                        },
                        {
                            "field": "sender",
                            "operator": "contains",
                            "value": "noreply@spam"
                        }
                    ]
                },
                {
                    "id": "action1",
                    "type": "action",
                    "name": "Reject Spam",
                    "action_type": "reject",
                    "reason": "Message identified as spam"
                },
                {
                    "id": "action2",
                    "type": "action",
                    "name": "Accept Email",
                    "action_type": "accept"
                }
            ],
            "connections": [
                {
                    "source": "trigger1",
                    "target": "filter1"
                },
                {
                    "source": "filter1",
                    "target": "action1",
                    "condition": "true"
                },
                {
                    "source": "filter1",
                    "target": "action2",
                    "condition": "false"
                }
            ]
        }
        
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            self.workflow_engine = WorkflowEngine(default_config)
            logger.info("Default workflow configuration created")
        except Exception as e:
            logger.error(f"Error creating default config: {e}")
    
    def process_email(self, email_content: str) -> Dict[str, Any]:
        """Process email through workflow"""
        try:
            # Parse email
            msg = email.message_from_string(email_content)
            
            # Extract email data
            email_data = {
                'from': msg.get('From', ''),
                'to': msg.get('To', ''),
                'subject': msg.get('Subject', ''),
                'date': msg.get('Date', ''),
                'message_id': msg.get('Message-ID', ''),
                'body': self._extract_body(msg),
                'size': len(email_content),
                'headers': dict(msg.items()),
                'timestamp': datetime.now().isoformat()
            }
            
            # Execute workflow
            if self.workflow_engine:
                result = self.workflow_engine.execute(email_data)
            else:
                result = {'action': 'accept', 'error': 'No workflow engine'}
            
            logger.info(f"Email processing result: {result.get('action', 'unknown')}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing email: {e}")
            return {'action': 'accept', 'error': str(e)}
    
    def _extract_body(self, msg) -> str:
        """Extract email body text"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            if msg.get_content_type() == "text/plain":
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        return body

def main():
    """Main entry point for the filter"""
    try:
        # Read email from stdin
        email_content = sys.stdin.read()
        
        if not email_content.strip():
            logger.error("No email content received")
            sys.exit(1)
        
        # Process email
        processor = EmailProcessor()
        result = processor.process_email(email_content)
        
        # Handle result
        action = result.get('action', 'accept')
        
        if action == 'reject':
            logger.info("Email rejected by workflow")
            sys.exit(1)  # Postfix will reject the email
        elif action == 'quarantine':
            # Move to quarantine folder
            quarantine_folder = result.get('quarantine_folder', '/var/mail/quarantine')
            os.makedirs(quarantine_folder, exist_ok=True)
            
            timestamp = int(time.time())
            quarantine_file = os.path.join(quarantine_folder, f"email_{timestamp}.eml")
            
            with open(quarantine_file, 'w') as f:
                f.write(email_content)
            
            logger.info(f"Email quarantined to: {quarantine_file}")
            sys.exit(1)  # Don't deliver to mailbox
        else:
            # Accept email (default action)
            logger.info("Email accepted by workflow")
            print(email_content)  # Pass through to next filter
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        print(email_content)  # Pass through on error
        sys.exit(0)

if __name__ == "__main__":
    main()