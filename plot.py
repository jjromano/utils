import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from sklearn.decomposition import PCA
from sklearn.metrics import confusion_matrix, roc_curve, f1_score
from sklearn.model_selection import learning_curve, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.tree import DecisionTreeClassifier, export_graphviz

import os
import pydotplus
import subprocess

# remove later?
from utils.data import table, rename
from rpy2.robjects import pandas2ri, r

#
def dummy_categorical(df, n):
    '''
    Creates a categorical column with labels 1 to n for testing purposes.

    ex) df['dummy'] = df.pipe(dummy_categorical, 5)
    '''

    size = df.shape[0] / n
    remainder = df.shape[0] - n * size

    a = []
    a.append(np.full((size + remainder, 1), 1))

    for i in range(2, n+1):
        a.append(np.full((size, 1), i))

    return pd.DataFrame(np.append(a[0], a[1:]))

#
def dummy_continuous(df, loc=0, scale=1):
    '''
    Creates a continuous column from a normal distribution for testing purposes.

    ex) df['dummy'] = df.pipe(dummy_continuous)
    '''

    return pd.DataFrame(np.random.normal(loc=loc, scale=scale, size=df.shape[0]))

#
def facet(df, row, col, **kwargs):
    '''
    Convenience function for creating seaborn facet grids.

    ex) df.pipe(facet, row='Type 1', col='Type 2').map(plt.scatter, 'Attack', 'Defense')
    '''

    return sns.FacetGrid(df, row=row, col=col, **kwargs)

#
def ceil_with_base(x, base):
    '''
    Takes the ceiling of a number with respect to any base.

    ex) ceil_with_base(0.03, 0.05) -> 0.05
    ex) ceil_with_base(0.02, 0.05) -> 0.05
    '''

    return base * np.ceil(float(x) / base)

#
def round_with_base(x, base):
    '''
    Rounds a number with respect to any base.

    ex) round_with_base(0.03, 0.05) -> 0.05
    ex) round_with_base(0.02, 0.05) -> 0
    '''

    return base * np.round(float(x) / base)

#
def nice_round(x):
    '''
    Rounds a number "nicely" to the nearest denomination of 5 or 10. Numbers less
    than 1 will be always be rounded upwards. Numbers greater than 1 may be rounded
    upwards or downwards.

    ex) nice_round(0.03) -> 0.05
    ex) nice_round(0.02) -> 0.05
    ex) nice_round(12) -> 10
    ex) nice_round(14) -> 15
    ex) nice_round(7) -> 7
    ex) nice_round(7.2) -> 7
    '''

    power = np.ceil(np.abs(np.log10(x))) - 1

    if x < 1:
        return ceil_with_base(x, base=5*10**-(power+1))

    else:
        return round_with_base(x, base=5*10**(power-1))

#
def truncate(x):
    '''
    Truncates a decimal to its first nonzero digit.

    ex) truncate(0.0345) -> 0.03
    '''

    if x == 0:
        return 0
    sign = -1 if x < 0 else 1
    scale = int(-np.floor(np.log10(abs(x))))
    if scale <= 0:
        scale = 1
    factor = 10**scale
    return sign * np.floor(abs(x) * factor) / factor

#
def nice_range_bin(ax, range=None):
    '''
    Helper function for matplotlib histograms to find the right range and number
    of bins so that the bar edges will line up nicely with existing x-axis tick
    marks.

    ex) fig, ax = plt.subplots()
        df[col].plot.hist(ax=ax)
        range, bins = nice_range_bin(ax)
    '''

    ticks = ax.get_xticks()

    if range is None:
        range = ticks[1], ticks[-2]

    total_length = range[1] - range[0]
    bin_size = ticks[1] - ticks[0]
    bins = int(total_length / bin_size)
    return range, bins

#
def take(iterator, n):
    '''
    Returns the nth item in an iterator.

    ex) take(df.groupby('Generation'), 2)
    '''

    for i, a in enumerate(iterator):
        if i != n:
            continue
        else:
            return a

#
def nice_hist(df, col, range=None, prop=False):
    '''
    Creates a "nice" histogram by drawing the default histogram first and then
    adjusting the bin edges so that they line up with the existing x-axis
    tick marks.

    This function takes advantage of the fact that matplotlib's
    plt.hist already comes up with "nice" values for the x-axis tick marks.

    Note: Does not play nicely with seaborn's FacetGrid.
    '''

    fig, ax = plt.subplots()
    df[col].plot.hist(range=range, ax=ax)
    range, bins = nice_range_bin(ax, range)
    plt.clf()

    if prop:
        weights = np.ones_like(df[col]) / float(len(df[col]))
    else:
        weights = None

    df[col].plot.hist(range=range, bins=bins, weights=weights, alpha=0.4)

#
def nice_hist2(a, bins=10, **kwargs):
    '''
    Creates a "nice" histogram by adjusting both the bin edges and the x-axis tick
    marks so that they line up nicely.

    Unlike nice_hist, this function uses custom functions to determine "nice"
    locations for the x-axis tick marks. This leads to tick values that are not
    as nice as the ones matplotlib's plt.hist gives.

    Note: Does not play nicely with seaborn's FacetGrid.
    '''

    heights, edges = np.histogram(a)
    width = (edges[-1] - edges[0]) / bins

    if width < 1:
        width = truncate(width)
    else:
        width = nice_round(width)

    new_edges = [round_with_base(edges[0], width) + i*width for i in range(len(edges))]
    plt.hist(a, bins=new_edges, **kwargs)
    plt.xticks(new_edges)

#
def prop_hist(a, prop=False, **kwargs):
    '''
    Creates a histogram where each bar displays the proportion of observations
    in each bin rather than their counts.
    '''

    if prop:
        weights = np.ones_like(a) / float(len(a))
    else:
        weights = None

    plt.hist(a, weights=weights, **kwargs)

#
def barplot(df, col, by=None, kind=None, prop=False):
    '''
    Creates a bar plot for a categorical variable. Group by an optional 2nd
    categorical variable.

    ex) df.pipe(barplot, col='HP', by='Type')
    '''

    if by:
        if prop:
            normalize = 'index'
        else:
            normalize = False

        data = df.pipe(table, col, by, normalize=normalize).unstack().reset_index()

        if kind == 'facet':
            g = sns.factorplot(x=0, y=col, col=by, data=data, kind='bar', orient='h')
            g.set_axis_labels('', col)

        elif kind == 'stack':
            values = data[by].unique()
            colors = sns.color_palette()
            for i in reversed(range(1, len(values)+1)):
                layer = data[data[by].isin(values[:i])]
                sns.barplot(x=0, y=col, data=layer, estimator=np.sum, ci=False,
                            orient='h', color=colors[i-1])

        else:
            sns.barplot(x=0, y=col, hue=by, data=data, orient='h')

    else:
        data = df[col].value_counts(normalize=prop).reset_index()
        sns.barplot(x=col, y='index', data=data, orient='h')
        plt.ylabel(col)

    plt.xlabel('')
    plt.legend(title=by, loc=(1, 0))

#
def boxplot(df, col, by, facet_by=None, sort_median=False):
    '''
    Creates a grouped box plot for a continuous variable. Facet by an optional
    3rd categorical variable.

    ex) df.pipe(boxplot, col='HP', by='Type')
    ex) df.pipe(boxplot, col='Amount', by='Category', facet_by='Target')
    '''

    if sort_median:
        order = df.groupby(by)[col].median().sort_values().index
    else:
        order = None

    if facet_by:
        g = sns.FacetGrid(df, col=facet_by)
        g.map(sns.boxplot, by, col, order=order)
    else:
        sns.boxplot(x=col, y=by, data=df, order=order, orient='h')

#
def distplot(df, col, by=None, prop=False, facet=False, range=None):
    '''
    Creates a histogram for a continuous variable. Group by an optional 2nd
    categorical variable.

    ex) df.pipe(distplot, col='HP', by='Type')
    '''

    if by:
        if facet:
            g = sns.FacetGrid(df, col=by)
            g.map(prop_hist, col, range=range)
            r, b = nice_range_bin(g.axes.flat[0], range)
            plt.clf()

            g = sns.FacetGrid(df, col=by, col_wrap=3)
            g.map(prop_hist, col, prop=prop, range=r, bins=b, alpha=0.4)
        else:
            for group, column in df.groupby(by)[col]:
                sns.kdeplot(column, label=group)
            plt.xlim(range)
            plt.legend(title=by, loc=(1, 0))

    else:
        nice_hist(df, col, prop=prop, range=range)

#
def heatplot(df, x, y, z=None, normalize=False):
    '''
    Creates a heatmap between 2 categorical variables. Calculate the mean for an
    optional 3rd continuous variable.

    ex) df.pipe(heatplot, x='Type 1', y='Type 2', z='Attack')
    '''

    if z:
        sns.heatmap(df.pipe(table, x, y, z), annot=True, fmt='.2f')
    else:
        sns.heatmap(df.pipe(table, x, y, normalize=normalize), annot=True, fmt='.2f')

#
def scatplot(df, x, y, by=None, facet=False):
    '''
    Creates a scatter plot for 2 continuous variables. Group by an optional 3rd
    categorical variable.

    ex) df.pipe(scatplot, x='Attack', y='Defense', by='Legendary')
    '''

    if by:
        if facet:
            g = sns.FacetGrid(df, col=by)
            g.map(sns.regplot, x, y, fit_reg=False, ci=False)
        else:
            sns.lmplot(x=x, y=y, hue=by, data=df, legend=False, fit_reg=False, ci=False)
            plt.legend(title=by, loc=(1, 0))
    else:
        sns.lmplot(x=x, y=y, hue=by, data=df, legend=False, fit_reg=False, ci=False)

#
def interactplot(df, col, by, val, heat=False):
    '''
    Creates an interaction lineplot or heatmap between 2 predictor variables and
    a 3rd target variable.

    ex) df.pipe(interactplot, col='Type 1', by='Type 2', val='Attack')
    '''

    a = df.pipe(table, col, by, val)

    if heat:
        sns.heatmap(a, annot=True, fmt='.2f')
    else:
        a.plot()
        plt.legend(title=by, loc=(1, 0))

#
def tsplot(df, date, by=None, val=None, freq='M', area=False):
    '''
    Creates a time series plot of counts for a date variable or of mean values
    for a continuous variable. Group by an optional 3rd categorical variable.

    ex) df.pipe(tsplot, date='date', by='Category')
    '''

    if area:
        kind = 'area'
    else:
        kind = 'line'

    if by and val:
        df.groupby([pd.Grouper(key=date, freq=freq), by])[val].mean().unstack(by).plot(kind=kind)
    elif by:
        df.groupby([pd.Grouper(key=date, freq=freq), by]).size().unstack(by).plot(kind=kind)
    elif val:
        df.groupby(pd.Grouper(key=date, freq=freq))[val].mean().plot(kind=kind)
    else:
        df.groupby(pd.Grouper(key=date, freq=freq)).size().plot(kind=kind)

    if by:
        plt.legend(title=by, loc=(1, 0))

#
def tsboxplot(df, date, col, freq='M'):
    '''
    Creates a time series boxplot for a continuous variable.

    ex) df.pipe(tsboxplot, date='date', col='Amount')
    '''

    groups = df.groupby(pd.Grouper(key=date, freq=freq))

    columns = []
    for i, g in groups:
        a = pd.DataFrame(g[col]).reset_index(drop=True).rename(columns={col: i})
        columns.append(a)

    data = pd.concat(columns, axis=1)
    sns.boxplot(data=data, orient='h')
    plt.xlabel(col)

#
def genboxplot(df, by, folder_name, default_dir='/Users/alexhuang/'):
    '''
    Generates boxplots for each column grouped by a fixed categorical variable
    and save them to a folder.

    ex) df.pipe(genboxplot, by='Target', folder_name='plots')
    '''

    directory = default_dir + folder_name + '/'
    if not os.path.exists(directory):
        os.makedirs(directory)

    df = df.copy()
    df = df.select_dtypes(include=[np.number])

    for i, col in enumerate(df.drop(by, 1)):
        sns.boxplot(df[col], df[by], orient='h')
        plt.xlabel('')
        plt.title(col)
        plt.savefig(directory + '%s.png' % i)
        plt.close()
        print 'Saved Plot: %s' % col

#
def pcaplot(df, by, method=None, sample_size=None):
    '''
    Creates a 2-D scatterplot of the entire dataset grouped by a categorical
    variable. Uses PCA method by default for dimensionality reduction.

    ex) df.pipe(pcaplot, by='Legendary')
    '''

    df = df.copy()

    if method is None:
        method = PCA()

    pipeline = make_pipeline(StandardScaler(), method)

    if sample_size:
        df = df.sample(sample_size)

    X = df.drop(by, 1)
    df['PCA 1'] = pipeline.fit_transform(X)[:, 0]
    df['PCA 2'] = pipeline.fit_transform(X)[:, 1]
    df.pipe(scatplot, x='PCA 1', y='PCA 2', by=by)

#
def plot_f1_scores(model, X, y):
    '''
    For each threshold value, calculates the mean 5-fold CV f1 score. Creates
    a lineplot of the threshold values vs. the f1 scores.

    ex) plot_f1_scores(model, X_train, y_train)
    '''

    cv = StratifiedKFold(n_splits=5, shuffle=True)

    cv_scores = []
    for threshold in np.linspace(.1, 1, 10):

        inner_cv_scores = []
        for train, test in cv.split(X, y):
            true = y.values[test]
            pred = model.predict_proba(X.values[test])[:, 1] > threshold
            inner_cv_scores.append(f1_score(true, pred))

        cv.scores.append(np.mean(inner_cv_scores))

    plt.plot(np.linspace(.1, 1, 10), cv_scores)

#
def plot_confusion_matrix(model, X, y, threshold=0.5, normalize=False):
    '''
    Creates a heatmap of the confusion matrix for the given model and data.

    ex) plot_confusion_matrix(model, X_test, y_test, normalize='index')
    '''

    try:
        pred = model.predict_proba(X)[:, 1] > threshold
    except:
        pred = model.predict(X)

    a = confusion_matrix(y, pred).astype(float)

    if normalize == 'index':
        a = np.divide(a, np.sum(a, 1).reshape(2, 1))
    elif normalize == 'column':
        a = np.divide(a, np.sum(a, 0))

    sns.heatmap(a, annot=True, fmt='.2f')
    plt.ylabel('True')
    plt.title('Predicted')

#
def plot_roc_curves(model, X, y):
    '''
    Creates a lineplot of the roc curve for the given model and data.

    ex) plot_roc_curves(model, X_test, y_test)
    '''

    try:
        pred = model.predict_proba(X)[:, 1]
    except:
        pred = model.predict(X)

    fpr, tpr, _ = roc_curve(y, pred)
    plt.plot(fpr, tpr)
    plt.plot([0, 1], [0, 1], linestyle='--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')

#
def plot_learning_curves(model, X, y):
    '''
    For each sample size, splits the given data into 5 CV train test pairs.
    Calulates the mean CV score over the 5 training sets and the mean CV score
    over the 5 validation sets. Creates a lineplot of the sample sizes vs.
    the mean CV train set scores and the mean CV validation set scores.

    ex) plot_learning_curves(model, X_train, y_train)
    '''

    cv = StratifiedKFold(n_splits=5, shuffle=True)
    sizes, train, validation = learning_curve(model, X, y, cv=cv, scoring='roc_auc')
    plt.plot(sizes, np.mean(train, axis=1), label='train')
    plt.plot(sizes, np.mean(validation, axis=1), label='validation')
    plt.xlabel('Sample Size')
    plt.ylabel('Performance')
    plt.legend(loc=(1, 0))
######

def plot_decision_tree(df, X, y, filename, **kwargs):
    #X = df[df.columns.difference([target])]
    #y = df[target]

    model = DecisionTreeClassifier(**kwargs)
    model.fit(X, y)
    dot_data = export_graphviz(model, out_file=None, feature_names=X.columns,
                               filled=True, class_names=y.astype(str).unique())
    graph = pydotplus.graph_from_dot_data(dot_data)
    graph.write_pdf(filename)
    subprocess.call(('open', filename))
    return model

def loess(df, col1, col2):
    pandas2ri.activate()
    dfr = pandas2ri.py2ri(df)

    a = r.loess('%s ~ %s' % (col2.replace('/', '.'), col1.replace('/', '.')), data=dfr)

    x = pd.DataFrame(np.array(a.rx2('x')))
    y = pd.DataFrame(np.array(a.rx2('fitted')))

    x_sorted = x.sort_values(by=0).index

    return x.loc[x_sorted], y.loc[x_sorted]

def compare_feature_sets_boot(a, b, col):
    a['data'] = 1
    b['data'] = 2

    c = pd.concat([a, b])[[col, 'data']]
    c.columns = ['Score_%s' % i for i in range(1, len(c.columns))] + ['data']

    sns.boxplot(y='variable', x='value', hue='data', data=c.melt('data'), orient='h')
    plt.legend(loc=(1,.5))

def compare_feature_sets_bar(a, b, col):
    a['data'] = 1
    b['data'] = 2

    pd.concat([a, b], axis=1)[[col]].plot.bar()
    plt.legend(loc=(1,.5))
