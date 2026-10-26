"""Export standalone research figures with raw timing samples and coverage."""
from pathlib import Path
import statistics
import sys


def render(report, summary, output, dependencies=None):
    if dependencies: sys.path.insert(0,str(Path(dependencies).resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    cells=[(t,m) for t in ('normal','interpreter') for m in ('off','calls','detail')]
    labels=['Normal JIT\ntrace off','Normal JIT\ncalls','Normal JIT\nvalues',
            'Interpreter\ntrace off','Interpreter\ncalls','Interpreter\nvalues']
    colors={'normal':'#2673a9','interpreter':'#b45309'}
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none'}):
        fig,axes=plt.subplots(1,3,figsize=(13.7,4.2),layout='constrained')
        for index,(tier,mode) in enumerate(cells):
            runs=[r for r in report['runs'] if (r['tier'],r['mode'])==(tier,mode)]
            values=[s['page_ms'] for r in runs for s in r['samples']]
            offsets=[(n-(len(values)-1)/2)*.035 for n in range(len(values))]
            axes[0].scatter([index+x for x in offsets],values,color=colors[tier],s=20,alpha=.7)
            median=statistics.median(values)
            axes[0].plot([index-.25,index+.25],[median,median],color='black',linewidth=2)
            axes[0].annotate(f'{median:g}',(index,median),xytext=(0,9),textcoords='offset points',ha='center',fontsize=8)
        axes[0].set(yscale='log',ylabel='Page duration (ms, log scale)',title='A. All timing samples; black line = median')
        axes[0].set_xticks(range(6),labels,fontsize=8);axes[0].grid(axis='y',alpha=.2)
        selected=[('normal','calls'),('normal','detail'),('interpreter','calls'),('interpreter','detail')]
        short=['JIT\ncalls','JIT\nvalues','Interpreter\ncalls','Interpreter\nvalues']
        for index,(tier,mode) in enumerate(selected):
            row=summary['cells'][tier+'/'+mode]
            coverage=statistics.median(row['coverage']['measuredLeaf'])
            axes[1].bar(index,coverage,width=.58,color=colors[tier])
            axes[1].text(index,coverage*1.6,f'{coverage*100:.5g}%',ha='center',fontsize=8)
            size=statistics.median(row['trace_bytes'])/1048576
            axes[2].bar(index,size,width=.58,color=colors[tier])
            axes[2].text(index,size*1.5,f'{size:.4g}',ha='center',fontsize=8)
        axes[1].set(yscale='log',ylim=(1e-6,4),ylabel='Known leaf calls recorded',title='B. Coverage, same invocation denominator')
        axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=1,decimals=4))
        axes[2].set(yscale='log',ylim=(.001,500),ylabel='Trace size (MiB, log scale)',title='C. Trace size per browser run')
        for axis in axes[1:]:axis.set_xticks(range(4),short,fontsize=8);axis.grid(axis='y',alpha=.2)
        fig.suptitle('Local call tracing: execution-tier policy, observation cost and coverage',fontsize=12)
        fig.supxlabel(f"{report['rounds']} rounds × {report['samples']} samples per cell. "
                      'Interpreter policy is diagnostic. No opcode trace measured.',fontsize=9)
        for suffix in ('svg','pdf','png'):
            fig.savefig(output/('TIER_COST.'+suffix),dpi=180)
        plt.close(fig)
    return matplotlib.__version__
