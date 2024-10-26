#!/usr/bin/env python3
import os

import yaml
import aws_cdk as cdk

from sbi_fpt.sbi_fpt_stack import SbiFptStack
from sbi_fpt.stack.java_stack import JavaStack
from sbi_fpt.stack.java_pipeline import PipelineJavaStack

app = cdk.App()

with open("parameters.yaml") as file:
    parameters = yaml.safe_load(file)
    
input_context = app.node.try_get_context('contxt')
context = parameters[input_context]
env = context['env']

SbiFptStack(app, "SbiFptStack",
    context=context,
    stack_name=f"{context['env']['prefix']}-{context['env']['environment']}-stack",
    description="Stack for creating vpc, ec2",
    env=cdk.Environment(account=env["account"], region=env["region"]))

JavaStack(app, "JavaStack",
    context=context,
    stack_name=f"{context['env']['prefix']}-{context['env']['environment']}-java-stack",
    description="Stack for creating ec2",
    env=cdk.Environment(account=env["account"], region=env["region"]))

PipelineJavaStack(app, "PipelineJavaStack",
    context=context,
    stack_name=f"{context['env']['prefix']}-{context['env']['environment']}-java-pipeline-stack",
    description="Stack for create pipeline ec2",
    )

app.synth()
