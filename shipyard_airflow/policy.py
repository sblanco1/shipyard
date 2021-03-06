# Copyright 2017 AT&T Intellectual Property.  All other rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import functools
import logging

import falcon
from oslo_config import cfg
from oslo_policy import policy

from shipyard_airflow.errors import ApiError, AppError

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
policy_engine = None


class ShipyardPolicy(object):
    """
    Initialize policy defaults
    """

    RULE_ADMIN_REQUIRED = 'rule:admin_required'

    # Base Policy
    base_rules = [
        policy.RuleDefault(
            'admin_required',
            'role:admin',
            description='Actions requiring admin authority'),
    ]

    # Orchestrator Policy
    task_rules = [
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:list_actions',
            RULE_ADMIN_REQUIRED,
            'List workflow actions invoked by users',
            [{
                'path': '/api/v1.0/actions',
                'method': 'GET'
            }]
        ),
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:create_action',
            RULE_ADMIN_REQUIRED,
            'Create a workflow action',
            [{
                'path': '/api/v1.0/actions',
                'method': 'POST'
            }]
        ),
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:get_action',
            RULE_ADMIN_REQUIRED,
            'Retreive an action by its id',
            [{
                'path': '/api/v1.0/actions/{action_id}',
                'method': 'GET'
            }]
        ),
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:get_action_step',
            RULE_ADMIN_REQUIRED,
            'Retreive an action step by its id',
            [{
                'path': '/api/v1.0/actions/{action_id}/steps/{step_id}',
                'method': 'GET'
            }]
        ),
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:get_action_validation',
            RULE_ADMIN_REQUIRED,
            'Retreive an action validation by its id',
            [{
                'path':
                '/api/v1.0/actions/{action_id}/validations/{validation_id}',
                'method': 'GET'
            }]
        ),
        policy.DocumentedRuleDefault(
            'workflow_orchestrator:invoke_action_control',
            RULE_ADMIN_REQUIRED,
            'Send a control to an action',
            [{
                'path': '/api/v1.0/actions/{action_id}/control/{control_verb}',
                'method': 'POST'
            }]
        ),
    ]

    # Regions Policy

    def __init__(self):
        self.enforcer = policy.Enforcer(cfg.CONF)

    def register_policy(self):
        self.enforcer.register_defaults(ShipyardPolicy.base_rules)
        self.enforcer.register_defaults(ShipyardPolicy.task_rules)

    def authorize(self, action, ctx):
        target = {'project_id': ctx.project_id, 'user_id': ctx.user_id}
        return self.enforcer.authorize(action, target, ctx.to_policy_view())


class ApiEnforcer(object):
    """
    A decorator class for enforcing RBAC policies
    """

    def __init__(self, action):
        self.action = action
        self.logger = LOG

    def __call__(self, f):
        @functools.wraps(f)
        def secure_handler(slf, req, resp, *args, **kwargs):
            ctx = req.context
            policy_eng = ctx.policy_engine
            slf.info(ctx, "Policy Engine: %s" % policy_eng.__class__.__name__)
            # perform auth
            slf.info(ctx, "Enforcing policy %s on request %s" %
                     (self.action, ctx.request_id))
            # policy engine must be configured
            if policy_eng is None:
                slf.error(
                    ctx,
                    "Error-Policy engine required-action: %s" % self.action)
                raise AppError(
                    title="Auth is not being handled by any policy engine",
                    status=falcon.HTTP_500,
                    retry=False
                )
            authorized = False
            try:
                if policy_eng.authorize(self.action, ctx):
                    # authorized
                    slf.info(ctx, "Request is authorized")
                    authorized = True
            except:
                # couldn't service the auth request
                slf.error(
                    ctx,
                    "Error - Expectation Failed - action: %s" % self.action)
                raise ApiError(
                    title="Expectation Failed",
                    status=falcon.HTTP_417,
                    retry=False
                )
            if authorized:
                return f(slf, req, resp, *args, **kwargs)
            else:
                slf.error(ctx,
                          "Auth check failed. Authenticated:%s" %
                          ctx.authenticated)
                # raise the appropriate response exeception
                if ctx.authenticated:
                    slf.error(ctx,
                              "Error: Forbidden access - action: %s" %
                              self.action)
                    raise ApiError(
                        title="Forbidden",
                        status=falcon.HTTP_403,
                        description="Credentials do not permit access",
                        retry=False
                    )
                else:
                    slf.error(ctx, "Error - Unauthenticated access")
                    raise ApiError(
                        title="Unauthenticated",
                        status=falcon.HTTP_401,
                        description="Credentials are not established",
                        retry=False
                    )

        return secure_handler


def list_policies():
    default_policy = []
    default_policy.extend(ShipyardPolicy.base_rules)
    default_policy.extend(ShipyardPolicy.task_rules)

    return default_policy
