# Generated from FormulaParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .FormulaParser import FormulaParser
else:
    from FormulaParser import FormulaParser

# This class defines a complete generic visitor for a parse tree produced by FormulaParser.

class FormulaParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by FormulaParser#program.
    def visitProgram(self, ctx:FormulaParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#moduleList.
    def visitModuleList(self, ctx:FormulaParser.ModuleListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#module.
    def visitModule(self, ctx:FormulaParser.ModuleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machine.
    def visitMachine(self, ctx:FormulaParser.MachineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineBody.
    def visitMachineBody(self, ctx:FormulaParser.MachineBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineSentenceConf.
    def visitMachineSentenceConf(self, ctx:FormulaParser.MachineSentenceConfContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineSentence.
    def visitMachineSentence(self, ctx:FormulaParser.MachineSentenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineProp.
    def visitMachineProp(self, ctx:FormulaParser.MachinePropContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineSigConfig.
    def visitMachineSigConfig(self, ctx:FormulaParser.MachineSigConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineSig.
    def visitMachineSig(self, ctx:FormulaParser.MachineSigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#machineSigIn.
    def visitMachineSigIn(self, ctx:FormulaParser.MachineSigInContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#model.
    def visitModel(self, ctx:FormulaParser.ModelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelBody.
    def visitModelBody(self, ctx:FormulaParser.ModelBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelSentence.
    def visitModelSentence(self, ctx:FormulaParser.ModelSentenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelContractConf.
    def visitModelContractConf(self, ctx:FormulaParser.ModelContractConfContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelContract.
    def visitModelContract(self, ctx:FormulaParser.ModelContractContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelFactList.
    def visitModelFactList(self, ctx:FormulaParser.ModelFactListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelFact.
    def visitModelFact(self, ctx:FormulaParser.ModelFactContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#cardSpec.
    def visitCardSpec(self, ctx:FormulaParser.CardSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelSigConfig.
    def visitModelSigConfig(self, ctx:FormulaParser.ModelSigConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelSig.
    def visitModelSig(self, ctx:FormulaParser.ModelSigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelIntro.
    def visitModelIntro(self, ctx:FormulaParser.ModelIntroContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#tSystem.
    def visitTSystem(self, ctx:FormulaParser.TSystemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#tSystemRest.
    def visitTSystemRest(self, ctx:FormulaParser.TSystemRestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transSteps.
    def visitTransSteps(self, ctx:FormulaParser.TransStepsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transStepConfig.
    def visitTransStepConfig(self, ctx:FormulaParser.TransStepConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transform.
    def visitTransform(self, ctx:FormulaParser.TransformContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transformRest.
    def visitTransformRest(self, ctx:FormulaParser.TransformRestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transBody.
    def visitTransBody(self, ctx:FormulaParser.TransBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transSentenceConfig.
    def visitTransSentenceConfig(self, ctx:FormulaParser.TransSentenceConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transSentence.
    def visitTransSentence(self, ctx:FormulaParser.TransSentenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transformSigConfig.
    def visitTransformSigConfig(self, ctx:FormulaParser.TransformSigConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transformSig.
    def visitTransformSig(self, ctx:FormulaParser.TransformSigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#transSigIn.
    def visitTransSigIn(self, ctx:FormulaParser.TransSigInContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domain.
    def visitDomain(self, ctx:FormulaParser.DomainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domSentences.
    def visitDomSentences(self, ctx:FormulaParser.DomSentencesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domSentenceConfig.
    def visitDomSentenceConfig(self, ctx:FormulaParser.DomSentenceConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domSentence.
    def visitDomSentence(self, ctx:FormulaParser.DomSentenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domainSigConfig.
    def visitDomainSigConfig(self, ctx:FormulaParser.DomainSigConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#domainSig.
    def visitDomainSig(self, ctx:FormulaParser.DomainSigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#config.
    def visitConfig(self, ctx:FormulaParser.ConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#sentenceConfig.
    def visitSentenceConfig(self, ctx:FormulaParser.SentenceConfigContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#settingList.
    def visitSettingList(self, ctx:FormulaParser.SettingListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#setting.
    def visitSetting(self, ctx:FormulaParser.SettingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modelParamList.
    def visitModelParamList(self, ctx:FormulaParser.ModelParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#valOrModelParam.
    def visitValOrModelParam(self, ctx:FormulaParser.ValOrModelParamContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#vomParamList.
    def visitVomParamList(self, ctx:FormulaParser.VomParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#update.
    def visitUpdate(self, ctx:FormulaParser.UpdateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#step.
    def visitStep(self, ctx:FormulaParser.StepContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#choiceList.
    def visitChoiceList(self, ctx:FormulaParser.ChoiceListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modApply.
    def visitModApply(self, ctx:FormulaParser.ModApplyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modArgList.
    def visitModArgList(self, ctx:FormulaParser.ModArgListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modAppArg.
    def visitModAppArg(self, ctx:FormulaParser.ModAppArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#stepOrUpdateLHS.
    def visitStepOrUpdateLHS(self, ctx:FormulaParser.StepOrUpdateLHSContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modRefs.
    def visitModRefs(self, ctx:FormulaParser.ModRefsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modRef.
    def visitModRef(self, ctx:FormulaParser.ModRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modRefRename.
    def visitModRefRename(self, ctx:FormulaParser.ModRefRenameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#modRefNoRename.
    def visitModRefNoRename(self, ctx:FormulaParser.ModRefNoRenameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#typeDecl.
    def visitTypeDecl(self, ctx:FormulaParser.TypeDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#typeDeclBody.
    def visitTypeDeclBody(self, ctx:FormulaParser.TypeDeclBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#funDecl.
    def visitFunDecl(self, ctx:FormulaParser.FunDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#fields.
    def visitFields(self, ctx:FormulaParser.FieldsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#field.
    def visitField(self, ctx:FormulaParser.FieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#mapArrow.
    def visitMapArrow(self, ctx:FormulaParser.MapArrowContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#unnBody.
    def visitUnnBody(self, ctx:FormulaParser.UnnBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#unnCmp.
    def visitUnnCmp(self, ctx:FormulaParser.UnnCmpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#typeId.
    def visitTypeId(self, ctx:FormulaParser.TypeIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#enumList.
    def visitEnumList(self, ctx:FormulaParser.EnumListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#enumCnst.
    def visitEnumCnst(self, ctx:FormulaParser.EnumCnstContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#ruleItem.
    def visitRuleItem(self, ctx:FormulaParser.RuleItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#compr.
    def visitCompr(self, ctx:FormulaParser.ComprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#comprRest.
    def visitComprRest(self, ctx:FormulaParser.ComprRestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#bodyList.
    def visitBodyList(self, ctx:FormulaParser.BodyListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#body.
    def visitBody(self, ctx:FormulaParser.BodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#constraint.
    def visitConstraint(self, ctx:FormulaParser.ConstraintContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#funcTermList.
    def visitFuncTermList(self, ctx:FormulaParser.FuncTermListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#funcOrCompr.
    def visitFuncOrCompr(self, ctx:FormulaParser.FuncOrComprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#funcTerm.
    def visitFuncTerm(self, ctx:FormulaParser.FuncTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#quoteList.
    def visitQuoteList(self, ctx:FormulaParser.QuoteListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#quoteItem.
    def visitQuoteItem(self, ctx:FormulaParser.QuoteItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#atom.
    def visitAtom(self, ctx:FormulaParser.AtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#id.
    def visitId(self, ctx:FormulaParser.IdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#constant.
    def visitConstant(self, ctx:FormulaParser.ConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#unOp.
    def visitUnOp(self, ctx:FormulaParser.UnOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#binOp.
    def visitBinOp(self, ctx:FormulaParser.BinOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#relOp.
    def visitRelOp(self, ctx:FormulaParser.RelOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FormulaParser#str.
    def visitStr(self, ctx:FormulaParser.StrContext):
        return self.visitChildren(ctx)



del FormulaParser